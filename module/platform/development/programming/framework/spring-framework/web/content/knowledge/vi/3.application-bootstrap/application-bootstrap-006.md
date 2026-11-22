# Phân biệt cấu hình Spring MVC trực tiếp với tự động cấu hình của Spring Boot

Cùng một endpoint Spring MVC có thể chạy trong ứng dụng **Spring Framework cấu hình trực tiếp** hoặc trong ứng dụng **Spring Boot có tự động cấu hình (auto-configuration)**. Cả hai vẫn dùng các thành phần cốt lõi của Spring MVC như `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, `HttpMessageConverter` và controller. Điểm khác nhau chính là **ai đăng ký, kết nối và cung cấp cấu hình mặc định** cho các thành phần đó.

Bài học này thuộc phần *Khởi tạo ứng dụng*: mục tiêu là hiểu trình tự khởi tạo, trách nhiệm cấu hình, ranh giới giữa Spring Framework và Spring Boot, cách giữ các mặc định hữu ích của Boot khi mở rộng Spring MVC, và khi nào nên tự nắm quyền cấu hình.

## 1. Phân biệt ba lớp trách nhiệm

Trước tiên tách ba lớp dễ bị đánh đồng:

1. **Spring Framework IoC container** (`ApplicationContext`, `@Configuration`, `@Bean`, `@ComponentScan`) tạo, quản lý và nối các bean. Nó không tự đồng nghĩa với một HTTP server.
2. **Spring Web MVC** là framework web dựa trên Servlet API. Nó cung cấp `DispatcherServlet` và hệ thống ánh xạ request tới controller, chuyển đổi dữ liệu, xử lý lỗi, view, v.v. Để tiếp nhận request HTTP, `DispatcherServlet` cần được đăng ký trong một Servlet container.
3. **Spring Boot** hỗ trợ khởi động ứng dụng và áp dụng **cấu hình có điều kiện** dựa trên classpath, loại ứng dụng, các bean đã tồn tại và property. Với ứng dụng Servlet có thư viện phù hợp, Boot có thể cấu hình web server nhúng, đăng ký `DispatcherServlet` và bổ sung các mặc định Spring MVC.

```text
                       SPRING MVC CỐT LÕI
                          DispatcherServlet
                           │            │
                        Mapping       Adapter
                           │            │
                         Controller → Service
                           │
                         Response

       SPRING FRAMEWORK TRỰC TIẾP                  SPRING BOOT
       ──────────────────────────                  ───────────
       Bạn đăng ký Servlet                         SpringApplication.run(...)
       Bạn bật cấu hình MVC                         Boot quyết định cấu hình áp dụng
       Bạn chọn và cấu hình container              Dùng embedded server khi phù hợp
       Bạn bổ sung tích hợp theo nhu cầu            Tự cung cấp nhiều mặc định
```

**Không có hai “loại Spring MVC” khác nhau**: Boot không thay `DispatcherServlet` bằng một bộ điều phối riêng. Controller viết bằng `@RestController` và `@GetMapping` vẫn sử dụng API Spring MVC. Spring Boot có thể tạo ứng dụng chạy dạng JAR với server nhúng, nhưng cũng có thể triển khai kiểu WAR trong môi trường thích hợp. Ứng dụng Spring Framework thuần cũng có thể dùng server nhúng nếu người phát triển tự cấu hình; ví dụ WAR bên dưới được chọn để làm rõ trách nhiệm đăng ký Servlet.

## 2. Cấu hình Spring MVC trực tiếp: tự lắp ghép tầng web

### 2.1. Việc bắt buộc phải có

Một ứng dụng Spring MVC truyền thống, dùng Servlet container bên ngoài, cần trả lời:

- **Servlet container nào** sẽ tiếp nhận kết nối HTTP? Ví dụ Apache Tomcat hỗ trợ phiên bản Jakarta Servlet phù hợp.
- **`DispatcherServlet` được tạo và map vào URL nào?** Ví dụ `/` hoặc `/api/*`.
- **`WebApplicationContext` chứa những bean nào?** Bao gồm controller/service và cấu hình MVC.
- **Ai đăng ký cấu hình hạ tầng MVC?** Thường dùng `@EnableWebMvc`, tương đương ý tưởng `<mvc:annotation-driven/>` của cấu hình XML.
- **Các tính năng ngoài mặc định cần gì?** JSON converter, resource handler, view resolver, multipart, exception advice, filter, interceptor, CORS... Tùy dependency và cấu hình, mỗi khả năng có điều kiện khác nhau.

`@EnableWebMvc` giúp đăng ký nhiều bean hạ tầng MVC như request mapping, argument resolver và message converter thích hợp với dependency. Nó **không tự khởi chạy Tomcat** và **không thay thế việc đăng ký `DispatcherServlet`**.

Có thể đăng ký `DispatcherServlet` bằng `web.xml`, `WebApplicationInitializer` hoặc lớp tiện ích `AbstractAnnotationConfigDispatcherServletInitializer`. Một root context và một Servlet context có thể được dùng theo kiến trúc phân tầng; không bắt buộc phải tạo cả hai khi ứng dụng nhỏ.

### 2.2. Ví dụ A — Spring MVC trực tiếp, đóng gói WAR

Ví dụ cố định nền tảng để tránh lẫn API: **Java 17+, Spring Framework 6.2.x, Jakarta Servlet 6.0 và Tomcat 10.1**. Tạo dự án Gradle riêng tên `manual-mvc` (có Gradle wrapper); file `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'war'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-webmvc:6.2.19'
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

`spring-webmvc` chứa hạ tầng Spring MVC; Servlet API chỉ cần khi biên dịch vì Tomcat sẽ cung cấp nó lúc chạy. Ví dụ trả chuỗi thuần để **không đòi hỏi thư viện JSON**. Nếu muốn `record` được serialize thành JSON, cần một converter/dependency thích hợp và kiểm tra cấu hình của MVC context.

File `src/main/java/demo/manual/WebConfig.java`:

```java
package demo.manual;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = WebConfig.class)
public class WebConfig {
}
```

Giải thích: `@Configuration` khai báo lớp cấu hình cho Spring container; `@ComponentScan` tìm controller và các thành phần nằm trong package `demo.manual` (kể cả package con); `@EnableWebMvc` nhập cấu hình hạ tầng MVC. Ba nhiệm vụ này không tương đương nhau.

File `src/main/java/demo/manual/AppInitializer.java`:

```java
package demo.manual;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class AppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}
```

Lớp này đăng ký `DispatcherServlet`, khởi tạo Servlet web application context với `WebConfig` và map Servlet tại `/`. Không có root context riêng trong ví dụ: controller và MVC infrastructure cùng nằm trong context của Servlet. **Mapping `/` là mapping trong web application**, không tự xóa context path khi đóng gói WAR.

File `src/main/java/demo/manual/GreetingController.java`:

```java
package demo.manual;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Đây là **ba file Java đầy đủ** trong dự án Gradle ở trên. Với wrapper đã có:

```bash
./gradlew clean war
```

Trên Windows PowerShell có thể chạy:

```powershell
.\gradlew.bat clean war
```

Triển khai file WAR từ `build/libs/` lên Tomcat 10.1 (chẳng hạn đặt tên triển khai là `manual-mvc.war`). Khởi động Tomcat và kiểm tra:

```bash
curl -i 'http://localhost:8080/manual-mvc/greet?name=Lan'
```

Khi deploy dưới context path `/manual-mvc`, response thành công có status **200 OK** và body văn bản:

```text
Xin chào, Lan!
```

Tên WAR và context path thực tế phụ thuộc cách bạn triển khai. Nếu WAR được triển khai thành root application, đường dẫn sẽ là `/greet`. Đây là ví dụ **runnable khi có Gradle/JDK/Tomcat như mô tả**, không phải `javac` đơn lẻ vì cần các dependency và Servlet container.

**Dòng khởi động trong mô hình trực tiếp:**

```text
Tomcat khởi động
  → phát hiện WebApplicationInitializer
  → AppInitializer đăng ký DispatcherServlet mapping "/"
  → WebApplicationContext được tạo
  → WebConfig kích hoạt MVC infrastructure + component scan
  → GreetingController trở thành bean/handler
  → GET /greet → DispatcherServlet → controller → String response
```

Ở đây container Servlet chủ động gọi quá trình khởi tạo web application. Đó là điểm khác với `SpringApplication.run` của Boot trong kiểu chạy JAR thông dụng.

### 2.3. Cấu hình trực tiếp không phải viết mọi thứ từ đầu

`@EnableWebMvc` cung cấp một baseline thực dụng cho Spring MVC. Bạn vẫn có thể cài `WebMvcConfigurer` để tùy chỉnh interceptor, view controller, formatter, CORS, resource handler, v.v. Ví dụ:

```java
@Configuration
@EnableWebMvc
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/start", "/greet");
    }
}
```

Đây là **minh họa cấu hình thay thế cho `WebConfig`**, cần import đúng các kiểu của Spring và giữ `@ComponentScan` nếu controller nằm ngoài khai báo bean. Không chép đè nguyên xi ví dụ rút gọn này vào dự án trên rồi quên component scan. Với cách đăng ký thủ công, bạn chịu trách nhiệm bảo đảm mọi phần cần thiết của ứng dụng đều được cấu hình tương thích.

## 3. Spring Boot: tự động cấu hình có điều kiện

### 3.1. Boot khởi tạo ứng dụng từ đâu?

`@SpringBootApplication` gộp ba nhóm hành vi chính:

- `@SpringBootConfiguration`: cho phép lớp ứng dụng tham gia cấu hình Spring, có ý nghĩa tương ứng với `@Configuration` trong kiểu ứng dụng này.
- `@EnableAutoConfiguration`: yêu cầu Boot xem xét các auto-configuration phù hợp.
- `@ComponentScan`: tìm các `@Component`, `@Controller`, `@Service`, `@Configuration`... ở package của application class và các package con theo mặc định.

`SpringApplication.run(...)` dựng Spring application context, xác định loại ứng dụng/web environment và kích hoạt chuỗi khởi tạo tương ứng. Với dependency Servlet MVC và server nhúng phù hợp, Boot có thể tạo embedded web server, đăng ký `DispatcherServlet` và lắp phần hạ tầng MVC.

Auto-configuration **không phải** “Boot quét mọi JAR rồi tạo mọi bean bất kể bạn có gì”. Các cấu hình được chọn khi thỏa điều kiện như:

| Điều kiện/đầu vào | Ý nghĩa trong quá trình cấu hình |
| --- | --- |
| `@EnableAutoConfiguration` / `@SpringBootApplication` | Bật cơ chế xét các auto-configuration |
| Classpath | Có class tương ứng như Servlet, DispatcherServlet và thư viện web |
| Loại ứng dụng | Servlet web application, reactive web application hoặc ứng dụng không web |
| Bean hiện có | Một số mặc định tự rút lui khi ứng dụng đã khai báo bean cùng trách nhiệm |
| Property | Bật/tắt/chỉnh hành vi khi có hỗ trợ |
| Các điều kiện khác | Ví dụ tài nguyên, cấu hình/bean khác và thứ tự áp dụng |

Các annotation dạng `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnWebApplication`, `@ConditionalOnProperty` là cơ chế điển hình. Một starter thường gom dependency phù hợp, trong khi **auto-configuration** là logic đăng ký bean có điều kiện; hai khái niệm liên quan nhưng không đồng nhất.

### 3.2. Ví dụ B — Spring Boot MVC với server nhúng

Để so sánh cùng endpoint `/greet`, tạo **một dự án riêng** tên `boot-mvc` với **Java 17+ và Spring Boot 3.5.7** (phiên bản cố định để ví dụ có thể tái lập; trong dự án thực hãy theo dòng phiên bản còn được hỗ trợ). File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
}
```

Không cần ghi trực tiếp version cho `spring-webmvc`, Servlet API hay embedded Tomcat vì hệ thống quản lý dependency của Boot phối hợp các phiên bản được hỗ trợ. File `src/main/java/demo/boot/BootMvcApplication.java`:

```java
package demo.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootMvcApplication.class, args);
    }
}
```

File `src/main/java/demo/boot/GreetingController.java`:

```java
package demo.boot;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Với wrapper Gradle đã có:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mở terminal khác:

```bash
curl -i 'http://localhost:8080/greet?name=Lan'
```

Status mong đợi **200 OK**, body:

```text
Xin chào, Lan!
```

Bạn cũng có thể đóng gói bằng `./gradlew bootJar` rồi chạy file JAR sinh ra trong `build/libs/` với `java -jar <ten-file-jar>`. Endpoint dùng đường dẫn `/greet` vì ở ví dụ JAR nhúng này **context path mặc định là gốc**. Nếu cấu hình context path khác, URL sẽ thay đổi.

**Dòng khởi tạo trong Boot JAR:**

```text
main()
  → SpringApplication.run(BootMvcApplication.class, args)
  → quét package demo.boot và các package con
  → xét các auto-configuration theo dependency/condition
  → tạo Servlet web application context + embedded server (nếu phù hợp)
  → đăng ký DispatcherServlet và MVC infrastructure
  → /greet được map tới GreetingController
  → HTTP request → cùng cơ chế xử lý của Spring MVC
```

`@SpringBootApplication` **không tự tạo endpoint**: controller vẫn phải được Spring tìm thấy và có mapping phù hợp. Nếu dời `GreetingController` ra ngoài package được scan mà không cấu hình lại, có thể nhận 404 dù ứng dụng Boot vẫn khởi động.

### 3.3. Boot tự cung cấp mặc định MVC gì?

Trong ứng dụng Servlet MVC Boot 3.x đủ dependency, những khả năng thường được cấu hình sẵn gồm:

- `DispatcherServlet` registration và các thành phần MVC phối hợp.
- Nhiều `HttpMessageConverter`, bao gồm JSON khi thư viện thích hợp hiện diện trên classpath.
- Hỗ trợ resource tĩnh từ các vị trí quy ước (chẳng hạn `classpath:/static/`, `classpath:/public/`) khi tính năng đang được bật.
- Một số `ViewResolver`, content negotiation, binding/conversion và hỗ trợ error handling theo cấu hình của Boot.
- Thiết lập qua property thay vì đăng ký lại toàn bộ cấu hình bằng Java code, ở những điểm Boot cho phép.

**Mặc định phụ thuộc phiên bản/điều kiện**. Không giả định rằng mọi converter, view resolver, security filter hay CORS rule sẽ xuất hiện trong mọi ứng dụng. Ví dụ Boot có starter web không đồng nghĩa API được xác thực hoặc CSRF/CORS đã cấu hình theo yêu cầu nghiệp vụ.

## 4. Bảng so sánh trực tiếp

| Tiêu chí | Spring MVC cấu hình trực tiếp | Spring Boot MVC tự động cấu hình |
| --- | --- | --- |
| Bộ máy xử lý request | `DispatcherServlet` của Spring MVC | Chính `DispatcherServlet` của Spring MVC |
| Ai kích hoạt khởi tạo web | Servlet container gọi initializer hoặc `web.xml`; có thể tự dựng embedded server | `SpringApplication.run` phối hợp auto-config và web server phù hợp |
| Ai đăng ký `DispatcherServlet` | Người phát triển đăng ký hoặc dùng initializer | Boot có auto-configuration đăng ký trong trường hợp đáp ứng điều kiện |
| Bật MVC infrastructure | Thường `@EnableWebMvc` hoặc XML tương đương | MVC auto-config của Boot cung cấp nền tảng, không cần `@EnableWebMvc` |
| Controller | `@Controller`, `@RestController`, `@RequestMapping`... | Cùng các annotation/controller đó |
| Component scan | Tự khai báo hoặc import các bean cần thiết | `@SpringBootApplication` cung cấp scan từ package gốc |
| Cấu hình mặc định | Spring MVC baseline cộng các thành phần bạn thêm | Baseline của Spring MVC cộng nhiều mặc định Boot, có điều kiện |
| Dependency | Tự chọn/đồng bộ thư viện | Dùng starter và quản lý phiên bản phụ thuộc tương thích |
| Đóng gói thường gặp | WAR trên container bên ngoài hoặc tự cấu hình embedded | JAR với embedded server; vẫn có thể làm WAR |
| Thay đổi cấu hình | Cấu hình trực tiếp theo nhu cầu | Property, custom bean, `WebMvcConfigurer`; hoặc chủ động takeover |
| Nhu cầu kiểm thử | Chú ý initializer/context, môi trường Servlet và dependency | Có hỗ trợ test slice/auto-config từ Boot, nhưng vẫn cần kiểm tra behavior thực |

Giữ lại một điểm: “ít dòng cấu hình hơn” không đồng nghĩa “framework ít hoạt động hơn”. Boot làm nhiều công việc đăng ký/configuration thay bạn, nhưng request vẫn đi qua Spring MVC.

## 5. Ba mức độ can thiệp vào MVC khi dùng Spring Boot

Đây là phần quan trọng khi dự án đã có Boot nhưng cần một chút tùy chỉnh.

### Mức 1 — Giữ Boot auto-config, đổi bằng property

Ưu tiên dùng property khi Boot có hỗ trợ rõ. Ví dụ đặt cổng chạy và prefix context path trong `src/main/resources/application.yml`:

```yaml
server:
  port: 9090
  servlet:
    context-path: /demo
```

Với ví dụ Boot, URL thành `http://localhost:9090/demo/greet?name=Lan`. Việc đổi context path là trách nhiệm container/server configuration; controller vẫn `@GetMapping("/greet")`.

Một số property liên quan `spring.mvc.*` hoặc `spring.web.*` có thể tùy chỉnh MVC. Tên và ý nghĩa property thay đổi giữa các dòng Boot; hãy đối chiếu reference của **đúng version** đang dùng. Không cần tạo lại nguyên một `DispatcherServlet` chỉ để đổi port hay context path.

### Mức 2 — Thêm WebMvcConfigurer, vẫn giữ Boot auto-config

Khi muốn tùy chỉnh MVC mà không thay nền tảng Boot, tạo class cấu hình triển khai `WebMvcConfigurer` **không gắn `@EnableWebMvc`**. Trong dự án Boot ví dụ, thêm file `src/main/java/demo/boot/MvcExtras.java`:

```java
package demo.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation
        .ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation
        .WebMvcConfigurer;

@Configuration
public class MvcExtras implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/start", "/greet");
    }
}
```

Khởi động lại và thử:

```bash
curl -i 'http://localhost:8080/start'
```

Một response redirect hợp lệ sẽ hướng tới `/greet` với status 3xx (thường là 302). Thử `curl -i -L ...` để theo redirect. Dùng `WebMvcConfigurer` để bổ sung interceptor, formatter, view controller hoặc CORS mapping là cách thông dụng để **mở rộng** MVC trong ứng dụng Boot. Với route/controller cụ thể, code nghiệp vụ vẫn nằm ở controller/service.

Điều quan trọng: `WebMvcConfigurer` là **extension point**, không phải dấu hiệu yêu cầu tắt toàn bộ auto-configuration. Một hoặc nhiều configurer có thể đóng góp tùy chỉnh; cần cẩn thận khi các cấu hình trùng/đè nhau.

### Mức 3 — Dùng @EnableWebMvc để tự nắm phần cấu hình MVC

Nếu thêm vào ứng dụng Boot:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class ManualMvcOwnership {
}
```

bạn đang nói: **Tôi muốn tự quản lý cấu hình hạ tầng Spring MVC, thay vì dùng phần MVC auto-configuration của Boot.**

Trong Boot 3.x, `WebMvcAutoConfiguration` được áp dụng có điều kiện khi ứng dụng Servlet có các lớp MVC thích hợp **và không có bean kiểu `WebMvcConfigurationSupport`**. `@EnableWebMvc` kích hoạt cấu hình MVC xây dựng trên cơ chế đó, khiến điều kiện tương ứng không còn phù hợp. Boot sẽ nhường phần MVC auto-config cho cấu hình người phát triển.

**Hệ quả cần phân biệt chính xác:**

- Các bean Spring MVC cơ bản do `@EnableWebMvc` cung cấp vẫn có thể hoạt động, nên endpoint `@GetMapping` **không nhất thiết biến mất**.
- Một số tiện ích/mặc định **chỉ do Boot MVC auto-config cung cấp** có thể mất hiệu lực hoặc cần bạn tái cấu hình: ví dụ phục vụ tài nguyên tĩnh theo quy ước hay cách tích hợp resolver/converter nhất định.
- Điều này **không tắt tất cả auto-configuration của Spring Boot**: embedded server, data source, các phần độc lập khác vẫn có thể được cấu hình nếu thỏa điều kiện tương ứng.
- Nếu muốn cấu hình thủ công triệt để, bạn chịu trách nhiệm xác định lại behavior mong đợi cho converter, static resources, formatter, view resolver, CORS và các phần MVC liên quan.

Ví dụ tình huống: `/greet` vẫn trả chuỗi nhưng `/style.css` được phục vụ theo cơ chế resource mặc định trước đó bắt đầu trả 404 sau khi bạn thêm `@EnableWebMvc`. Đừng chỉ nhìn thấy 404 rồi suy ra `DispatcherServlet` hỏng; hãy kiểm tra resource handler và điều kiện của MVC auto-config.

### 5.1. `WebMvcConfigurer` không đồng nghĩa với `WebMvcConfigurationSupport`

Tên giống nhau dễ gây nhầm:

- `WebMvcConfigurer`: **interface extension point**, có thể dùng trong Boot để bổ sung cấu hình **trong khi vẫn giữ** MVC auto-config.
- `WebMvcConfigurationSupport`: **class hạ tầng MVC**; sự tồn tại của bean kiểu này là điều kiện để Boot MVC auto-config back off trong Boot 3.x.
- `@EnableWebMvc`: nhập cấu hình MVC dựa trên `DelegatingWebMvcConfiguration` (một nhánh của `WebMvcConfigurationSupport`), nên có tác động ở mức sở hữu cấu hình MVC.
- Đừng tự tạo subclass `WebMvcConfigurationSupport` chỉ để thêm một interceptor hay formatter thông thường. Dùng `WebMvcConfigurer` khi tính năng được extension point hỗ trợ.

Với nhu cầu thay riêng các thành phần như `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter` hay `ExceptionHandlerExceptionResolver`, Boot 3.x còn có các extension point như `WebMvcRegistrations`; đây là tình huống chuyên sâu, không cần dùng cho một cấu hình MVC đơn giản.

## 6. “Back off” thực chất là gì?

**Back off** nghĩa là một auto-configuration **bỏ qua một phần hoặc toàn bộ cấu hình mặc định có điều kiện** khi phát hiện ứng dụng đã cung cấp thành phần có cùng vai trò. Nó không tự động có nghĩa Boot dừng chạy, xóa bean của người dùng hoặc mọi auto-config đều bị vô hiệu.

Ví dụ minh họa nguyên tắc bằng mã cấu hình tùy biến của riêng bạn:

```java
@AutoConfiguration
@ConditionalOnClass(SmtpClient.class)
class MailExampleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailSender.class)
    MailSender defaultMailSender() {
        return new DefaultMailSender();
    }
}
```

Đây là **mã giả minh họa điều kiện**, không phải ví dụ Java độc lập: `SmtpClient`, `MailSender`, `DefaultMailSender` là các kiểu giả định, không phải API Spring tiêu chuẩn. Nếu `SmtpClient` không có trên classpath hoặc đã có bean `MailSender`, phương thức cấu hình mặc định sẽ không đăng ký bean. Hình thức annotation và nguyên tắc là thật; tên class trong ví dụ này chỉ dùng để dễ hiểu.

Áp dụng trở lại Spring MVC:

```text
Auto-configuration được cân nhắc
  │
  ├── Thiếu Servlet/web MVC trên classpath? → Không áp dụng phần MVC
  │
  ├── Không phải Servlet web application?   → Không áp dụng phần Servlet MVC
  │
  ├── Đã có WebMvcConfigurationSupport?      → WebMvcAutoConfiguration back off
  │
  └── Các điều kiện tương ứng đều hợp lệ     → Đăng ký MVC defaults của Boot
```

Các điều kiện là đặc tả của **một phiên bản Boot cụ thể**, không phải quy tắc cố định cho mọi thế hệ Spring. Không suy từ việc có một `@Bean` bất kỳ rằng tất cả bean MVC mặc định sẽ bị loại.

## 7. Điều gì xảy ra khi request đến?

Cùng request `GET /greet?name=Lan`, dù cách khởi tạo khác, pipeline Spring MVC tương đồng:

1. HTTP request tới Servlet container qua host, port và context path.
2. Servlet container chuyển request cho `DispatcherServlet` đã được đăng ký.
3. `HandlerMapping` tìm handler tương ứng với URL, method và các điều kiện mapping khác.
4. `HandlerAdapter` thực thi controller method, xử lý argument như `@RequestParam`.
5. Controller trả về `String`; do sử dụng `@RestController`, giá trị được đưa vào HTTP response body qua cơ chế MVC phù hợp.
6. Server gửi status, header và body về client.

```text
                   manual WAR                Boot JAR
                  ┌────────────┐            ┌────────────┐
Browser → HTTP →  │ Tomcat WAR │            │ Embedded   │ ← HTTP ← Browser
                  │ + Servlet  │            │ Servlet    │
                  └─────┬──────┘            └──────┬─────┘
                        │                          │
                        ▼                          ▼
                  DispatcherServlet          DispatcherServlet
                        │                          │
                        └────────────┬─────────────┘
                                     ▼
                            @GetMapping("/greet")
                                     ▼
                          "Xin chào, Lan!"
```

Khác nhau về deploy và default config không có nghĩa một endpoint tự động nhanh hơn/chậm hơn endpoint kia. Hiệu năng thực còn phụ thuộc dependency, bộ nhớ, threading, converter, logic nghiệp vụ, I/O và cấu hình deployment. Không lấy việc hai cách trả giống body để kết luận vòng đời bean hoặc cấu hình middleware cũng hoàn toàn giống nhau.

## 8. Chẩn đoán khi “Boot không tự cấu hình như dự kiến”

### 8.1. Dùng Condition Evaluation Report

Spring Boot có thể hiển thị report lý do auto-configuration được chọn hoặc bị bỏ qua khi bật debug:

```bash
./gradlew bootRun --args='--debug'
```

Hoặc khi chạy JAR:

```bash
java -jar build/libs/boot-mvc-1.0.0.jar --debug
```

Tên JAR trong lệnh thứ hai là **ví dụ tương ứng với tên project/version demo**; nếu file thực tế có tên khác, thay bằng đường dẫn từ `build/libs/`.

Trong output, tìm phần **CONDITIONS EVALUATION REPORT** và các entry liên quan `WebMvcAutoConfiguration`, `DispatcherServletAutoConfiguration`, web server. Report giúp trả lời: auto-config nào match, điều kiện nào không match, class hay bean nào gây back off. Cần đọc đúng phần positive/negative matches; log debug không đảm bảo tự sửa lỗi.

Nếu có thêm Spring Boot Actuator và cấu hình endpoint phù hợp, `/actuator/conditions` có thể cung cấp thông tin tương tự; endpoint này **không mặc nhiên được bật công khai** và cần quản lý quyền truy cập.

### 8.2. Bảng tình huống thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Boot app chạy nhưng endpoint 404 | Controller nằm ngoài package scan, sai method/path/context path | Xác nhận `@SpringBootApplication` package, mapping và context path |
| Lỗi không tìm được Servlet/DispatcherServlet | Thiếu dependency MVC/Servlet hoặc dùng sai loại web app | Xem dependency graph, starter và conditions report |
| WAR manual trả 404 | `DispatcherServlet` chưa được đăng ký, sai WAR context path hoặc thiếu scan | Xem log Tomcat, `AppInitializer`, mapping `/`, URL thực tế |
| WAR manual lỗi class `javax.servlet.*` / `jakarta.servlet.*` | Kết hợp sai đời Spring/Servlet container | Với Spring 6 dùng `jakarta.*` và container tương thích |
| Sau khi thêm `@EnableWebMvc`, CSS/JS tĩnh không còn hoạt động | Boot MVC auto-config đã nhường quyền; resource handler thiếu | Xem conditions report, bỏ annotation nếu không cần takeover |
| JSON serialize/deserialize lỗi | Converter/Jackson không có, MIME type không hợp hoặc binding lỗi | Kiểm tra dependency, `Content-Type`, message converter |
| Thêm `WebMvcConfigurer` nhưng interceptor không chạy | Config ngoài component scan, pattern sai, request không đi qua chain mong đợi | Xác nhận bean đã đăng ký và request mapping |
| Đã định nghĩa bean mà Boot vẫn cấu hình thứ khác | Bean không cùng kiểu/điều kiện; cấu hình chỉ back off một phần | Đọc điều kiện của auto-config cụ thể |
| Tưởng `@SpringBootApplication` thay `@RestController` | Annotation ứng dụng chỉ bootstrap/scan/auto-config | Controller cần bean + mapping thực tế |
| Đổi `server.port` nhưng gọi cổng cũ | Port đã thay, config khác override, hoặc app chạy với profile khác | Xem log web server và effective configuration |

### 8.3. Quy trình kiểm tra ngắn

Khi có lỗi startup hoặc routing, hãy đi theo thứ tự:

1. **Dependency:** có đúng Servlet MVC stack không (`spring-webmvc`, starter web) và không trộn nhầm API `javax.*`/`jakarta.*`?
2. **Bootstrap:** container đã chạy? `SpringApplication.run`/initializer đã được gọi và `DispatcherServlet` đã đăng ký?
3. **Context:** controller bean có được tạo trong đúng application context chưa?
4. **Mapping:** method, URL, context path và servlet mapping thực tế có khớp request không?
5. **MVC configuration:** ứng dụng có `@EnableWebMvc`/`WebMvcConfigurationSupport` gây back off không? `WebMvcConfigurer` có đăng ký đúng không?
6. **Converter/resource/error behavior:** endpoint hoạt động nhưng JSON, static file hoặc view bị lỗi là vấn đề khác với thiếu Servlet.
7. **Condition report:** dùng dữ liệu lúc chạy để xác định cái gì đã match thay vì đoán theo annotation.

## 9. Chọn cách cấu hình theo nhu cầu

**Dùng Spring MVC trực tiếp** khi bạn cần tích hợp framework vào môi trường Servlet có sẵn, tự quản chặt lifecycle và hệ thống bean, hoặc đang học/duy trì ứng dụng Spring MVC không dùng Boot. Bạn cần hiểu rõ container, đăng ký Servlet, dependency, context hierarchy và các thành phần MVC.

**Dùng Spring Boot MVC** khi muốn ứng dụng web khởi động nhất quán, dependency dễ quản lý và tận dụng các cấu hình mặc định có điều kiện. Đây thường là cách thuận tiện cho service mới, nhưng bạn vẫn cần hiểu cơ chế gốc để debug.

**Trong ứng dụng Boot đã tồn tại**, chọn mức thay đổi nhỏ nhất phù hợp: property cho thiết lập sẵn có; `WebMvcConfigurer` cho nhiều tùy chỉnh MVC; `@EnableWebMvc` chỉ khi thực sự muốn nhận trách nhiệm quản lý phần lớn cấu hình MVC. Tùy chỉnh `@Bean` có thể chỉ khiến một phần auto-config nhường chỗ; phải kiểm tra điều kiện cụ thể.

## 10. Sai lầm thường gặp và câu hỏi tự kiểm tra

**Sai lầm 1:** “`@EnableWebMvc` là annotation bắt buộc trong mọi Spring Boot web app.” Thực tế Boot MVC auto-config thường thay nhu cầu đó; thêm `@EnableWebMvc` có thể vô hiệu phần cấu hình MVC do Boot cung cấp.

**Sai lầm 2:** “Spring Boot tự động cấu hình nên không có `DispatcherServlet`.” Spring MVC trong Boot vẫn dùng `DispatcherServlet`; Boot chỉ phụ trách đăng ký và thiết lập nhiều phần.

**Sai lầm 3:** “Có `@RestController` là endpoint tự hoạt động.” Lớp phải được đăng ký bean, có MVC infrastructure và được Servlet container chuyển request tới.

**Sai lầm 4:** “`WebMvcConfigurer` sẽ tắt auto-config.” `WebMvcConfigurer` là cơ chế bổ sung cấu hình; `@EnableWebMvc` hoặc bean hạ tầng sở hữu MVC mới là tình huống cần đặc biệt xem xét.

**Sai lầm 5:** “Spring MVC thuần bắt buộc phải dùng XML và server ngoài; Boot luôn chỉ tạo executable JAR.” Cả Java config/initializer và `web.xml` đều hợp lệ. Spring MVC có thể được tự gắn với embedded server; Boot cũng hỗ trợ WAR khi đúng cấu hình.

**Sai lầm 6:** “Auto-config luôn ghi đè bean tự khai báo.” Nhiều auto-config đặt điều kiện về bean đã tồn tại, nhưng không phải mọi trường hợp đều giống nhau. Quyền ưu tiên cần xem source/conditions của cấu hình cụ thể.

Tự kiểm tra:

1. Vì sao `@EnableWebMvc` không tự mở port 8080? Thành phần nào thực sự nhận kết nối HTTP?
2. Trong ví dụ manual WAR, lớp nào đăng ký `DispatcherServlet` và lớp nào kích hoạt MVC infrastructure?
3. Trong ví dụ Boot, `@SpringBootApplication` gồm ba hành vi chính nào? Điều kiện nào quyết định MVC auto-config được áp dụng?
4. Hai endpoint `/greet` có cùng controller logic nhưng context path khác nhau khi chạy WAR và Boot JAR ra sao?
5. Nếu chỉ muốn thêm redirect `/start → /greet`, vì sao `WebMvcConfigurer` phù hợp hơn việc takeover bằng `@EnableWebMvc`?
6. Nếu một static file ngừng hoạt động sau khi thêm `@EnableWebMvc`, hãy mô tả nguyên nhân có thể có và cách chứng minh bằng conditions report.
7. Giải thích sự khác nhau giữa `@ConditionalOnMissingBean`, `WebMvcConfigurer`, `WebMvcConfigurationSupport` và khái niệm **back off**.
8. Nếu xóa starter web và chỉ giữ một số thư viện Spring cơ bản, vì sao không nên giả định Boot vẫn tạo `DispatcherServlet` và web server?

**Đạt yêu cầu** khi bạn có thể vẽ luồng khởi tạo cả hai cách, chạy hai endpoint, chỉ ra đúng nơi `DispatcherServlet` được đăng ký, chọn được property/`WebMvcConfigurer`/`@EnableWebMvc` theo nhu cầu và sử dụng condition report để xác minh một giả thuyết cấu hình.

### Tài liệu kỹ thuật để đối chiếu với phiên bản đang dùng

- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — Enable MVC Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html
- Spring Boot 3.5 — Servlet Web Applications / Spring MVC Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
