# WebApplicationContext gốc, ngữ cảnh servlet và quan hệ cha–con

## 1. Vấn đề cần hiểu khi khởi tạo ứng dụng Spring MVC

Khi phát triển ứng dụng Spring MVC, bạn sẽ gặp nhiều đối tượng có tên gần giống nhau: `ApplicationContext`, `WebApplicationContext`, `ServletContext`, `DispatcherServlet` và `ContextLoaderListener`. Chúng có chức năng khác nhau. Nếu không phân biệt, rất dễ gặp lỗi controller không được ánh xạ, service không được inject, cùng một bean bị khởi tạo hai lần hoặc cấu hình MVC bị đặt sai chỗ.

Một ứng dụng web có thể tổ chức **một context Spring duy nhất** hoặc **một hệ phân cấp context cha–con**. Trong kiểu phân cấp cổ điển:

- **Root `WebApplicationContext`** (ngữ cảnh gốc) là nơi chứa các bean dùng chung cho ứng dụng, ví dụ service, repository, data source, transaction manager hoặc cấu hình hạ tầng.
- **Servlet-specific `WebApplicationContext`** (ngữ cảnh dành riêng cho một `DispatcherServlet`) thường chứa controller, handler mapping, view resolver, message converter và cấu hình web của servlet đó.
- Root là **parent**; servlet context là **child**. Child có thể tra cứu bean của parent, còn parent không mặc nhiên thấy bean chỉ được khai báo trong child.
- Một ứng dụng có thể có nhiều `DispatcherServlet`, mỗi servlet có child context riêng, cùng tham chiếu một root context.

**Điểm quan trọng:** Root–child là **một lựa chọn tổ chức** của Spring MVC trên Servlet stack; đây không phải điều kiện bắt buộc của mọi ứng dụng Spring Web, đặc biệt trong các ứng dụng Spring Boot hiện đại.

## 2. Phân biệt năm khái niệm thường bị nhầm

| Thành phần | Thuộc hệ thống nào? | Trách nhiệm | Có giữ bean Spring? |
|---|---|---|---|
| `ApplicationContext` | Spring Core | IoC container: tạo, quản lý, liên kết các bean; quản lý cấu hình, sự kiện, lifecycle | Có |
| `WebApplicationContext` | Spring Web | Mở rộng `ApplicationContext` cho môi trường web Servlet; truy cập `ServletContext` và các đối tượng liên quan | Có |
| `ServletContext` | Jakarta Servlet API | Đại diện môi trường của web application trong Servlet container; lưu attributes và thông tin ứng dụng web | Không phải Spring IoC container |
| `DispatcherServlet` | Spring MVC | Front controller nhận HTTP request, tìm handler, phối hợp các chiến lược MVC và tạo response | Không phải IoC container; sử dụng một `WebApplicationContext` |
| `ContextLoaderListener` | Spring Web trên Servlet | Khởi tạo và hủy root `WebApplicationContext` theo vòng đời web application | Không phải container, mà là thành phần bootstrap |

`WebApplicationContext` là interface mở rộng `ApplicationContext`, không phải một bean đặc biệt duy nhất có tên "webApplicationContext". Có nhiều cách triển khai, ví dụ `AnnotationConfigWebApplicationContext` và `XmlWebApplicationContext`. Cùng một ứng dụng có thể sở hữu nhiều context Spring, nhưng **mỗi context có bean registry và phạm vi quản lý riêng**.

`ServletContext` thường được Servlet container (ví dụ Tomcat) cấp cho một web application. Nó không phải servlet-specific Spring child context. Cụm “servlet context” trong chủ đề bài học cần hiểu rõ theo ngữ cảnh: **`ServletContext`** (API Jakarta) khác với **`WebApplicationContext` của `DispatcherServlet`** (Spring). Tên gần giống nhau nhưng đối tượng và trách nhiệm khác nhau.

## 3. Sơ đồ root context và servlet child context

```text
                    Servlet container (ví dụ Tomcat)
                                  |
                      ServletContext (Jakarta)
                                  |
                    +-------------+-------------+
                    |                           |
          ContextLoaderListener           Servlet registrations
                    |                           |
                    v                    +------+------+
       Root WebApplicationContext         |             |
       (các bean dùng chung)              v             v
            - OrderService           DispatcherServlet A  DispatcherServlet B
            - OrderRepository             |             |
            - DataSource                  v             v
            - TransactionManager       Child A        Child B
                    ^                  (web MVC)       (web MVC)
                    |                     |             |
                    +------ parent -------+             |
                    +-------- parent -------------------+
                                          |             |
                                    controllers A  controllers B
                                    mappings A     mappings B
                                    views A        views B
```

Mũi tên `parent` mô tả quan hệ Spring `ApplicationContext.getParent()`, **không phải** quan hệ kế thừa class Java. Mỗi child vẫn có bean definitions, scope và lifecycle của riêng nó; chỉ việc tra cứu và sử dụng bean có thể đi lên parent.

Nếu chỉ có một `DispatcherServlet`, mô hình vẫn tương tự:

```text
Root WebApplicationContext
    ├── UserService
    └── UserRepository
          ↑ parent của
Servlet WebApplicationContext
    ├── UserController
    ├── HandlerMapping
    ├── HandlerAdapter
    └── ViewResolver
          ↑ được dùng bởi
     DispatcherServlet
```

**Mục đích phân tách:** Các servlet có thể dùng chung tầng nghiệp vụ nhưng độc lập về endpoint, view hoặc cấu hình web. Ví dụ một servlet phục vụ vùng người dùng, một servlet phục vụ vùng quản trị. Không nên tạo nhiều servlet hoặc nhiều context chỉ để “kiến trúc trông rõ tầng” khi một context đã đủ.

## 4. Root WebApplicationContext là gì?

Root context là `WebApplicationContext` cấp ứng dụng web, thường được khởi tạo sớm bởi `ContextLoaderListener` trong kiểu triển khai WAR trên Servlet container. Nó có thể chứa:

- Service nghiệp vụ: `CustomerService`, `OrderService`, v.v.
- Repository và các dependency của tầng truy cập dữ liệu.
- DataSource, transaction manager, client gọi hệ thống ngoài.
- Các bean hạ tầng cần được chia sẻ giữa các servlet context.

Ví dụ cấu hình root bằng Java:

```java
package com.example.hierarchy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RootConfig {
    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
```

`GreetingService` là một class Java thông thường; trong ví dụ này `@Bean` đăng ký nó vào **root context**. Việc root có tên “root” không khiến mọi class tự động trở thành bean trong root: bean xuất hiện ở context nào phụ thuộc vào cấu hình được nạp ở context đó.

Khi root tồn tại, Spring đặt tham chiếu root `WebApplicationContext` trong attribute của Jakarta `ServletContext`. Để tra cứu root từ thành phần servlet cấp thấp, Spring cung cấp `WebApplicationContextUtils.getWebApplicationContext(servletContext)` hoặc `getRequiredWebApplicationContext(servletContext)`; thao tác này lấy **root**, không phải tự chọn child của mọi `DispatcherServlet`.

### Root context không bắt buộc

Một ứng dụng nhỏ có thể chỉ có servlet-specific `WebApplicationContext`. Khi không cần chia sẻ hạ tầng giữa nhiều servlet, việc tách root và child có thể làm cấu hình phức tạp không cần thiết. `AbstractAnnotationConfigDispatcherServletInitializer` cho phép trả `null` ở `getRootConfigClasses()` để không tạo root riêng.

Ngược lại, khi đặt tất cả cấu hình ở root và trả `null` tại `getServletConfigClasses()`, Spring MVC cũng hỗ trợ cách tổ chức không cần phân tách web và shared config thành hai nhóm; tuy nhiên cần hiểu cách initializer và `DispatcherServlet` sử dụng context tương ứng. Khi học quan hệ cha–con, nên dùng hai cấu hình tách biệt để dễ quan sát.

## 5. Servlet-specific WebApplicationContext là gì?

`DispatcherServlet` sử dụng một `WebApplicationContext` dành cho chính nó. Đây là nơi điển hình để cấu hình:

- Controller (`@Controller`, `@RestController`).
- `HandlerMapping` và `HandlerAdapter` để phát hiện, gọi phương thức xử lý HTTP.
- View resolver, template/view configuration.
- HTTP message converters, formatters, validators.
- Các cấu hình MVC như `@EnableWebMvc`, `WebMvcConfigurer`.

Ví dụ cấu hình child:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {
    @Bean
    public GreetingController greetingController(
            GreetingService greetingService,
            ApplicationContext applicationContext) {
        return new GreetingController(greetingService, applicationContext);
    }
}
```

Ở đây:

1. `WebConfig` được đăng ký vào **child**.
2. `GreetingController` trở thành bean của child.
3. `GreetingService` chỉ được đăng ký ở root nhưng được truyền vào bean controller trong child nhờ tra cứu qua parent.
4. `ApplicationContext` được inject khi tạo bean ở child là context đang tạo bean đó; có thể dùng để quan sát `getParent()`.

Trong cấu hình cổ điển, mỗi `DispatcherServlet` có thể nhận một child context khác nhau, điều này cho phép hai servlet có bộ controller/view riêng. Việc một servlet quản lý route nào còn tùy **Servlet mapping** (ví dụ `/api/*` hay `/admin/*`) và các request mappings bên trong Spring MVC.

### Đừng mặc định controller trong root sẽ được DispatcherServlet phát hiện

Handler mapping mặc định của Spring MVC thường dò controller trong **context của chính DispatcherServlet**. Các bean từ parent có thể được inject vào child, nhưng việc tìm **handler methods** trong ancestor context không được bật mặc định ở các handler mapping phổ biến. Do đó, để rõ ràng và tránh hành vi phụ thuộc cấu hình, hãy đặt controller và cấu hình MVC ở child; đặt service/repository dùng chung ở root.

Nếu vô tình cấu hình component scan bao trùm toàn bộ package ở cả root và child, cùng một component có thể được tạo thành **hai bean khác nhau**, dẫn đến service state riêng, khởi tạo tài nguyên trùng hoặc mapping khó đoán.

## 6. Quan hệ cha–con: cách Spring tra cứu bean

Đặc điểm cốt lõi của phân cấp `ApplicationContext` là **tra cứu đi từ child lên parent** khi child không có bean phù hợp.

Xét cây bean:

```text
ROOT
  bean: auditService
  bean: greetingService

CHILD /api
  bean: apiController
  bean: greetingFormatter

CHILD /admin
  bean: adminController
  bean: adminViewResolver
```

Các kết luận quan trọng:

| Thao tác | Kết quả thường thấy |
|---|---|
| `/api` child lấy `greetingService` | Có thể tìm được bean ở root |
| `/admin` child lấy `auditService` | Có thể tìm được bean ở root |
| Root tìm `apiController` | Không tự nhìn xuống child để tìm |
| `/api` child tìm `adminController` | Không tự nhìn sang sibling child |
| Child có bean cùng tên với bean ở root | Bean local cùng tên có thể che bean ở parent trong đường tra cứu của child |

Nếu child chứa bean tên `greetingService` và root cũng chứa `greetingService`, tìm theo tên từ child thường lấy bean local. Tuy nhiên, **tra cứu theo kiểu (`getBean(SomeType.class)` hoặc autowiring) có thêm quy tắc candidate, primary, qualifier và độ ưu tiên**; đừng suy diễn mọi trường hợp trùng tên và trùng kiểu đều giải quyết như nhau. Đặt bean name rõ ràng, giới hạn component scan và dùng `@Qualifier` khi thật sự cần.

Bean singleton cũng phải hiểu theo phạm vi **một container**: `singleton` nghĩa là một instance cho mỗi bean definition trong một `ApplicationContext`, không tự bảo đảm chỉ có một object duy nhất trong toàn JVM. Hai context cùng scan và đăng ký `@Service` có thể có hai singleton khác nhau.

### Parent có thể bị thay đổi động không?

Về mặt API, context có cơ chế thiết lập parent trong một số giai đoạn khởi tạo. Trong thực tế, nên xác định cấu trúc phân cấp **trước khi refresh context** và giữ ổn định. Thay parent của context đang vận hành hoặc tùy ý đóng root trong khi child còn dùng bean của root có thể gây hành vi khó kiểm soát.

## 7. Ai khởi tạo root và child, theo thứ tự nào?

Trong ứng dụng WAR kiểu Spring MVC không dùng bootstrap của Spring Boot, Servlet container bắt đầu vòng đời web application và cơ chế startup thường diễn ra như sau:

1. Servlet container khởi tạo `ServletContext`.
2. Spring Servlet initializer hoặc cấu hình `web.xml` đăng ký `ContextLoaderListener` và một hay nhiều `DispatcherServlet`.
3. Khi `ContextLoaderListener` được gọi theo vòng đời khởi động của web application, nó tạo và `refresh` root `WebApplicationContext`, đăng ký các bean chung và công bố root qua `ServletContext`.
4. `DispatcherServlet` được khởi tạo; nó sử dụng hoặc tạo `WebApplicationContext` của mình, thiết lập quan hệ parent khi có root và khởi tạo các chiến lược MVC cần thiết.
5. Servlet container ánh xạ URL theo Servlet mapping; request đến `DispatcherServlet` được xử lý bằng bean MVC ở context của servlet, có thể inject bean từ root.
6. Khi web application dừng, các thành phần khởi tạo context tương ứng dọn lifecycle và đóng các context mà chúng quản lý.

Thứ tự và chi tiết startup còn phụ thuộc cách đăng ký servlet, `load-on-startup` và chiến lược bootstrap. Đây là một luồng điển hình, không phải hướng dẫn tự gọi `refresh()` trong controller hoặc tạo `ApplicationContext` mỗi request.

### ContextLoaderListener và DispatcherServlet có phải cùng một đối tượng?

Không. `ContextLoaderListener` là **listener** cấp web application để bootstrap root; `DispatcherServlet` là **servlet** xử lý HTTP và có context riêng. Cả hai có thể tham gia vào quá trình startup nhưng có trách nhiệm độc lập. Nếu bạn chỉ dùng một context, có thể không cần `ContextLoaderListener` riêng.

## 8. Ví dụ chạy được: một root context và một servlet child

Ví dụ dưới đây minh họa chính xác đường truyền dependency và cơ chế tìm parent. Nó sử dụng **Spring Framework 6.2.x**, **Java 17+**, **Jakarta Servlet 6** và triển khai dưới dạng **WAR trên Tomcat 10.1** hoặc container tương thích. Đây là kiểu bootstrap Servlet truyền thống, không sử dụng Spring Boot.

Cấu trúc dự án Maven:

```text
spring-context-hierarchy-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/hierarchy/
                ├── AppInitializer.java
                ├── RootConfig.java
                ├── WebConfig.java
                ├── GreetingService.java
                └── GreetingController.java
```

### 8.1. Khai báo dependency và đóng gói WAR

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-context-hierarchy-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webmvc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <finalName>context-demo</finalName>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-webmvc` kéo theo các thành phần Spring MVC cần thiết. `jakarta.servlet-api` có scope `provided` vì Tomcat cung cấp Servlet API khi chạy. Không cần `web.xml` vì Spring có cơ chế initializer theo Servlet specification.

### 8.2. Tạo service dùng chung và root config

Tệp `GreetingService.java`:

```java
package com.example.hierarchy;

public class GreetingService {
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

Tệp `RootConfig.java`:

```java
package com.example.hierarchy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RootConfig {
    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
```

`GreetingService` được đăng ký **duy nhất trong root**. Không cần `@Service` vì được khai báo bằng `@Bean`. Cách này tránh scan trùng và giúp việc phân biệt bean owner rõ ràng.

### 8.3. Tạo controller thuộc child

Tệp `GreetingController.java`:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;
    private final ApplicationContext context;

    public GreetingController(
            GreetingService service,
            ApplicationContext context) {
        this.service = service;
        this.context = context;
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello(@RequestParam(defaultValue = "Lan") String name) {
        return service.greet(name);
    }

    @GetMapping(value = "/context", produces = MediaType.TEXT_PLAIN_VALUE)
    public String contextInfo() {
        ApplicationContext parent = context.getParent();
        return "hasParent=" + (parent != null)
                + ", parentHasService="
                + (parent != null && parent.containsLocalBean("greetingService"))
                + ", childHasController="
                + context.containsLocalBean("greetingController");
    }
}
```

Tệp `WebConfig.java`:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {
    @Bean
    public GreetingController greetingController(
            GreetingService service,
            ApplicationContext context) {
        return new GreetingController(service, context);
    }
}
```

Giải thích:

- `@EnableWebMvc` đăng ký hạ tầng MVC trong **servlet child context**.
- `GreetingController` là bean được định nghĩa tại child qua `@Bean`, đồng thời có annotation `@RestController`/`@GetMapping` để Spring MVC nhận diện HTTP handler.
- `GreetingService` không tồn tại cục bộ trong child; dependency injection đi lên root để lấy bean.
- Endpoint `/context` cho phép kiểm tra trực tiếp quan hệ parent và vị trí đăng ký bean.
- Do chỉ trả chuỗi text, ví dụ không yêu cầu cấu hình Jackson/JSON serialization.

### 8.4. Đăng ký cả hai context

Tệp `AppInitializer.java`:

```java
package com.example.hierarchy;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class AppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return new Class<?>[] { RootConfig.class };
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

`AbstractAnnotationConfigDispatcherServletInitializer` hỗ trợ đăng ký `DispatcherServlet` và các context cấu hình Java. Khi `getRootConfigClasses()` trả về `RootConfig.class`, Spring tạo root context; khi `getServletConfigClasses()` trả về `WebConfig.class`, Spring tạo servlet context với root làm parent. Servlet mapping `"/"` đưa các URL của ứng dụng tới `DispatcherServlet` này.

**Chú ý cú pháp import:** Java cho phép ngắt dòng giữa các token phân tách bởi whitespace, nhưng không được ngắt giữa một tên định danh đơn. Để dễ đọc và copy, import có thể viết trên một dòng như sau:

```java
import org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer;
```

### 8.5. Biên dịch, triển khai và quan sát kết quả

Đặt các tệp vào đúng package `com.example.hierarchy` và chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests package
```

Maven tạo WAR tại `target/context-demo.war`. Sao chép WAR vào thư mục `webapps` của Tomcat 10.1 và khởi động Tomcat. Nếu ứng dụng được triển khai với context path mặc định dựa trên tên WAR `/context-demo` và Tomcat đang nghe cổng 8080, gọi:

```bash
curl -s "http://localhost:8080/context-demo/hello?name=Lan"
```

Nội dung phản hồi dự kiến:

```text
Hello Lan
```

Tiếp tục kiểm tra cấu trúc context:

```bash
curl -s "http://localhost:8080/context-demo/context"
```

Nội dung phản hồi dự kiến:

```text
hasParent=true, parentHasService=true, childHasController=true
```

Đây là các giá trị dự kiến khi WAR triển khai đúng, context mapping giữ nguyên, cấu hình không bị sửa và request chưa bị filter/proxy khác can thiệp. Khi truy cập ứng dụng triển khai ở context path khác, thay tiền tố `/context-demo` tương ứng.

Cách tự đọc kết quả:

- `hasParent=true`: controller đang ở child có parent.
- `parentHasService=true`: `greetingService` được đăng ký **cục bộ trong root**, không phải một bean tình cờ được tạo ở child.
- `childHasController=true`: `greetingController` được đăng ký cục bộ trong context mà `DispatcherServlet` sử dụng.
- `/hello` chạy được: child sử dụng thành công dependency `GreetingService` từ parent.

Ví dụ dùng Spring MVC trên Servlet container; không dùng `javac`/ `java` đơn lẻ để chạy một class độc lập vì phải có các dependency, quy trình đóng gói WAR và Servlet container.

## 9. Cách cấu hình tương đương bằng web.xml

Trong các hệ thống truyền thống hoặc legacy, root context và servlet context được khai báo trong `web.xml`. Ví dụ rút gọn sau minh họa cấu hình dựa trên XML (các file `/WEB-INF/root-context.xml` và `/WEB-INF/api-servlet.xml` phải tồn tại và có cấu hình bean hợp lệ):

```xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <context-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>/WEB-INF/root-context.xml</param-value>
    </context-param>

    <listener>
        <listener-class>
            org.springframework.web.context.ContextLoaderListener
        </listener-class>
    </listener>

    <servlet>
        <servlet-name>api</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>
        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>/WEB-INF/api-servlet.xml</param-value>
        </init-param>
        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>api</servlet-name>
        <url-pattern>/api/*</url-pattern>
    </servlet-mapping>
</web-app>
```

Đây là **mảnh cấu hình giải thích**, không phải ví dụ chạy độc lập: nó yêu cầu hai tệp XML Spring tương ứng và một ứng dụng WAR đầy đủ. Chức năng khác nhau:

- `context-param/contextConfigLocation` ở cấp `web-app` hướng dẫn `ContextLoaderListener` nạp root.
- `init-param/contextConfigLocation` bên trong `<servlet>` hướng dẫn `DispatcherServlet` nạp cấu hình riêng của nó.
- `servlet-mapping` quyết định phần URI do servlet đó phục vụ.

**Không trộn cả `web.xml` và Java initializer để cùng đăng ký root/servlet một cách vô ý.** Nếu dự án đã dùng một cơ chế bootstrap, kiểm tra cấu hình hiện tại trước khi thêm cơ chế thứ hai.

## 10. Nếu có hai DispatcherServlet thì chia sẻ và cách ly ra sao?

Giả sử ứng dụng có:

```text
Root:  sharedService, repository, transactionManager
   |
   +-- Child A (DispatcherServlet "public")
   |     +-- PublicController
   |     +-- các cấu hình MVC public
   |
   +-- Child B (DispatcherServlet "admin")
         +-- AdminController
         +-- các cấu hình MVC admin
```

`PublicController` và `AdminController` có thể inject cùng bean `sharedService` từ root. Nếu cả hai servlet không đăng ký lại bean cùng tên/kiểu, chúng tham chiếu cùng đối tượng root singleton. Nhưng `PublicController` không thể tùy ý lấy `AdminController` chỉ bằng cách lookup trong Child A.

Cần thiết kế các Servlet URL mappings không gây mâu thuẫn, ví dụ `/public/*` và `/admin/*`. Bên trong từng servlet, path mapping của controller được đánh giá theo cách ánh xạ request vào servlet đó. Chức năng phân quyền không tự được thực thi chỉ vì có servlet riêng; vẫn cần cơ chế security phù hợp.

**Tại sao không đặt tất cả controller vào root?** Vì handler discovery và cấu hình web của mỗi servlet cần rõ ràng, đồng thời root nên chỉ giữ phần thực sự cần chia sẻ. Nếu root chứa cả các controller với mapping giống nhau và child bật quét ancestor handlers tùy biến, có thể tạo ra mapping trùng hoặc khó dự đoán.

## 11. Spring Boot thường có kiến trúc context khác

Nhiều tài liệu về Spring MVC truyền thống mô tả bắt buộc có `ContextLoaderListener` root và `DispatcherServlet` child. Cách hiểu đó **không đúng cho mọi ứng dụng Spring Boot**.

Trong Spring Boot Servlet web application thông thường:

- Boot khởi động Spring application context và embedded Servlet container theo cơ chế cấu hình của Boot.
- Boot tự đăng ký và cấu hình `DispatcherServlet` cùng các thành phần MVC cần thiết.
- Controller, service, repository thường cùng nằm trong **một application context** được component scan từ gói chứa class `@SpringBootApplication`.
- Thường không cần tự khai báo `ContextLoaderListener` hoặc viết `AbstractAnnotationConfigDispatcherServletInitializer`.
- Một `DispatcherServlet` trong Boot không có nghĩa mặc nhiên sẽ có một servlet child context độc lập giống sơ đồ WAR cổ điển.

Ví dụ Boot đơn giản:

```java
@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
```

Đây là **đoạn minh họa**, chưa chạy độc lập vì lược bỏ imports, dependency, classpath và cấu hình dự án. Khi dùng Spring Boot, hãy kiểm tra context thật sự được tạo thay vì chỉ suy diễn từ tên `DispatcherServlet`.

Có thể có context hierarchy trong một ứng dụng Boot nếu được cấu hình rõ ràng cho một nhu cầu đặc biệt, nhưng đó là lựa chọn chủ động và đòi hỏi hiểu quyền sở hữu context, component scan và bootstrap. Với ứng dụng thông thường, một context đơn giản là đủ.

## 12. Tình huống lỗi phổ biến và cách kiểm tra

### 12.1. Controller không được tìm thấy, request trả 404

Khả năng thường gặp:

- Controller chỉ được đăng ký ở root trong khi servlet child tìm handler ở context local.
- Root/child scan sai package hoặc config class không được nạp vào context dự định.
- Servlet mapping không khớp URL (ví dụ servlet phục vụ `/api/*` nhưng request được gửi đến đường dẫn khác).
- `@GetMapping` và HTTP method/path không khớp, hoặc ứng dụng có context path khác.

Cách kiểm tra là đối chiếu URL gồm **application context path + servlet mapping + controller mapping**; kiểm tra bean controller nằm ở context nào và log startup của Spring MVC.

### 12.2. NoSuchBeanDefinitionException khi inject service

Ví dụ controller ở child cần `OrderService` nhưng không tìm thấy. Các nguyên nhân có thể là `OrderService` chưa được đăng ký, root config chưa được nạp, bean được tạo ở sibling child hoặc package scan không bao gồm class đó.

Đừng vội thêm `@ComponentScan` tràn lan vào child để “cho tìm thấy service”. Nếu service cần dùng chung, đăng ký tại root và xác minh child tham chiếu đúng parent.

### 12.3. Service bị khởi tạo hai lần

Nếu root và child cùng `@ComponentScan("com.example")`, cùng một `@Service` có thể được tạo ở cả hai nơi. Kiểm tra:

- Phạm vi package do mỗi config scan.
- Bean names và bean definitions cục bộ (`containsLocalBean`).
- `ApplicationContext.getParent()` để biết bean trong parent.
- Các `@Bean` factory methods có khai báo trùng không.

Giới hạn component scan theo mục đích: root quét thành phần dùng chung; child quét controller/cấu hình MVC. Trong dự án lớn, có thể dùng `includeFilters`, `excludeFilters` hoặc tách package rõ ràng.

### 12.4. Một bean ở root cố inject controller ở child

Parent **không tra cứu xuống child theo cơ chế thông thường**, nên injection có thể thất bại. Đây thường là dấu hiệu đảo ngược phụ thuộc kiến trúc: service ở root không nên phụ thuộc trực tiếp vào HTTP controller. Dùng service abstraction hoặc ứng dụng event/message phù hợp để tầng nghiệp vụ độc lập với web.

### 12.5. Cấu hình MVC bị đặt nhầm context

`@EnableWebMvc`, các `HandlerMapping`, `HandlerAdapter`, `ViewResolver` thường nên thuộc child của servlet cần sử dụng chúng trong cấu trúc phân cấp. Nếu chỉ có một context, chúng nằm trong context đó. Đừng xem `@EnableWebMvc` là annotation phải thêm vào mọi context.

Đặc biệt với Spring Boot, việc tự thêm `@EnableWebMvc` có thể thay đổi cơ chế cấu hình MVC tự động của Boot. Chỉ bật chủ động khi hiểu và muốn tự kiểm soát cấu hình MVC.

### 12.6. Web scope không hoạt động như dự kiến

`request` và `session` là các scope gắn với web request/session, khác singleton của context. Việc sử dụng scope web đòi hỏi môi trường web thích hợp và truy cập trong phạm vi HTTP request tương ứng. Có root/child không tự làm cho mọi thread bất kỳ có request scope hoạt động; tác vụ nền hoặc thread tự tạo thường không có request attributes của một HTTP request.

### 12.7. Việc gọi getBean(...) cho kết quả khó hiểu

Các phương thức như `containsBean`, `containsLocalBean`, `getBean`, `getBeanNamesForType` có semantics khác nhau với context hierarchy. Đặc biệt, việc tìm bean names chỉ cục bộ có thể không bao gồm ancestor beans. Khi debug, luôn ghi rõ bạn đang xem **root** hay **child** và API tra cứu có tính đến ancestors hay không. Spring cũng có tiện ích `BeanFactoryUtils` để tra cứu theo phân cấp trong những trường hợp cần.

## 13. Tự kiểm tra hiểu biết

**Câu 1.** Trong cấu hình WAR hai context, `CustomerController` ở child cần `CustomerService` ở root. Có thể inject được không?  
**Giải đáp:** Có, nếu service được đăng ký đúng root, child liên kết đúng parent và không có xung đột bean candidate.

**Câu 2.** `CustomerService` ở root có thể inject trực tiếp `CustomerController` chỉ tồn tại ở child không?  
**Giải đáp:** Không theo cơ chế parent lookup thông thường. Parent không tự truy cập bean chỉ tồn tại trong child.

**Câu 3.** Nếu có hai `DispatcherServlet`, có bắt buộc có hai root context không?  
**Giải đáp:** Không. Một root có thể được chia sẻ bởi nhiều servlet-specific child contexts.

**Câu 4.** `ServletContext` của Tomcat và `WebApplicationContext` của Spring có phải cùng kiểu container không?  
**Giải đáp:** Không. `ServletContext` thuộc Jakarta Servlet API; `WebApplicationContext` là Spring IoC container có khả năng tương tác với môi trường Servlet.

**Câu 5.** Một ứng dụng Spring Boot REST có `@RestController` và `@Service` có bắt buộc phải cài `ContextLoaderListener` và child context riêng không?  
**Giải đáp:** Không. Boot thông thường tự bootstrap ứng dụng web và các thành phần MVC, thường chỉ cần một application context.

**Câu 6.** `@Service` được scan ở cả root và child có bảo đảm chỉ một singleton trên toàn ứng dụng không?  
**Giải đáp:** Không. Singleton được quản lý theo bean definition/context; scan trùng có thể tạo hai instance.

**Câu 7.** Một `DispatcherServlet` có thể tự động gọi controller chỉ tồn tại trong child của servlet khác không?  
**Giải đáp:** Không. Hai child là sibling, không có cơ chế tự tìm bean của nhau.

## 14. Tài liệu tham chiếu

- [Spring Framework Reference — DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): vai trò `DispatcherServlet`, bootstrap ứng dụng web và liên kết Servlet environment.
- [Spring Framework Reference — Context Hierarchy](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/context-hierarchy.html): mô hình root và servlet-specific child, chia sẻ bean, Java initializer và cấu hình tương đương qua `web.xml`.
- [Spring Framework Reference — Servlet Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/container-config.html): đăng ký `DispatcherServlet` bằng cấu hình Java.
- [Spring Framework Reference — ApplicationContext Hierarchies in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html): cách kiểm tra hierarchy trong integration tests.
- [Javadoc — AbstractAnnotationConfigDispatcherServletInitializer](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/servlet/support/AbstractAnnotationConfigDispatcherServletInitializer.html): API cấu hình root/servlet và hành vi khi không dùng root riêng.

**Ghi nhớ:** `WebApplicationContext` là Spring IoC container dành cho môi trường web; `ServletContext` là đối tượng Servlet API. Trong mô hình hierarchy của Spring MVC, root giữ bean dùng chung và mỗi `DispatcherServlet` có thể có child context giữ bean web riêng; child thấy parent, parent không tự thấy child. Cấu trúc này hữu ích trong WAR/multi-servlet, còn ứng dụng Spring Boot thông thường thường hoạt động tốt với một application context.
