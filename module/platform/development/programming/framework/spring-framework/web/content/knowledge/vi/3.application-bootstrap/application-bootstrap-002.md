# Đăng ký `DispatcherServlet` bằng Java và nhận biết cấu hình `web.xml`

## 1. Mục tiêu và bối cảnh

Sau bài này, bạn có thể:

1. Giải thích vì sao ứng dụng Spring MVC cần đăng ký `DispatcherServlet` với **Servlet container**.
2. Khởi tạo Spring MVC bằng Java thông qua `AbstractAnnotationConfigDispatcherServletInitializer`, không bắt buộc có `web.xml`.
3. Nhận biết cách viết trực tiếp `WebApplicationInitializer` và `ServletContext.addServlet(...)`.
4. Đọc cấu hình Servlet truyền thống trong `WEB-INF/web.xml` và đối chiếu từng phần với Java configuration.
5. Phân biệt **Servlet registration**, **Spring application context**, **Spring MVC configuration** và **Spring Boot auto-configuration**.
6. Xây dựng, đóng gói WAR, triển khai, gọi endpoint và xác định nguyên nhân một số lỗi khởi tạo thường gặp.

**Phạm vi:** Spring MVC trên **Jakarta Servlet stack**, minh họa bằng Java 17+, Spring Framework 6.2 và Tomcat 10.1. Các phiên bản cũ có thể dùng namespace `javax.servlet.*` và sơ đồ khởi tạo khác; không trộn `javax` và `jakarta` trong cùng ví dụ.

## 2. Tại sao phải đăng ký `DispatcherServlet`?

### 2.1. Servlet container và Spring MVC có trách nhiệm khác nhau

Trong ứng dụng WAR chạy trên Tomcat, Jetty hoặc Servlet container khác:

- **Servlet container** nhận kết nối HTTP, quản lý vòng đời Servlet, Filter, Listener và ánh xạ URL tới Servlet.
- **`DispatcherServlet`** là Servlet trung tâm của Spring MVC. Sau khi container chuyển request đến đây, nó tìm handler/controller phù hợp, xử lý dữ liệu đầu vào và tạo kết quả HTTP.
- **Spring `WebApplicationContext`** giữ các bean Spring (controller, service, converter, `HandlerMapping`, `HandlerAdapter`, …) phục vụ Servlet.

```text
          HTTP GET /mvc-demo/hello
                       |
               Tomcat / Servlet container
                       |
             Servlet URL mapping: "/"
                       |
               DispatcherServlet
                       |
              Spring WebApplicationContext
                       |
      HandlerMapping -> HandlerAdapter -> @GetMapping
                       |
                HelloController
                       |
               HTTP 200 + response body
```

Kể cả khi có một class mang `@RestController`, request **chưa thể đến class đó** nếu Servlet container không khởi tạo/ánh xạ HTTP entry point và Spring không tạo context chứa controller. Nói cách khác, **đăng ký Servlet** và **khai báo controller** là hai công việc khác nhau.

### 2.2. Cơ chế đăng ký Java lúc khởi động

Từ Servlet 3.0, container hỗ trợ đăng ký `Servlet` bằng Java. Trong ứng dụng Spring MVC truyền thống:

1. Khi triển khai WAR, Servlet container dùng cơ chế `ServletContainerInitializer` theo đặc tả Jakarta Servlet để tìm các initializer.
2. Spring cung cấp `SpringServletContainerInitializer`, được tìm thấy nhờ khai báo service-provider trong JAR thích hợp.
3. Initializer của Spring tìm các implementation hợp lệ của `WebApplicationInitializer` trên classpath ứng dụng và gọi `onStartup(ServletContext)`.
4. Mã khởi tạo tạo hoặc chỉ định Spring `WebApplicationContext`, đăng ký `DispatcherServlet`, khai báo URL mapping và thiết lập tải sớm.
5. Container khởi tạo `DispatcherServlet`; Servlet kết nối với Spring MVC infrastructure; HTTP request bắt đầu được điều phối.

Khi dùng `AbstractAnnotationConfigDispatcherServletInitializer`, class cha thực hiện phần đăng ký lặp lại ở bước 4. Vì thế ứng dụng **không cần tự viết `web.xml`** chỉ để khai báo dispatcher.

Lưu ý: cơ chế discovery còn phụ thuộc cấu hình Servlet container, WAR được đóng gói đúng và các initializer không bị vô hiệu hóa/bỏ sót trong quá trình quét. Một class có tên `WebAppInitializer` không đủ; class phải thừa kế/triển khai đúng SPI.

## 3. Cách ưu tiên: `AbstractAnnotationConfigDispatcherServletInitializer`

### 3.1. Ba phương thức quyết định cấu hình

Class `org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer` cung cấp cách khai báo ngắn gọn:

```java
package example.web;

import org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer;

public class WebAppInitializer
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

Ý nghĩa của từng phương thức:

| Phương thức | Giá trị trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| `getRootConfigClasses()` | `null` | Không tạo root Spring context riêng. Bài thực hành nhỏ chỉ cần context của dispatcher. |
| `getServletConfigClasses()` | `WebConfig.class` | Khai báo Java `@Configuration` dùng cho `WebApplicationContext` thuộc `DispatcherServlet`. |
| `getServletMappings()` | `"/"` | Đăng ký dispatcher làm **default Servlet mapping** của ứng dụng web, cho phép ánh xạ các đường dẫn như `/hello`. |

**Điểm dễ nhầm:** `getServletMappings()` không phải là annotation `@GetMapping`. Mapping `"/"` đưa một nhóm request **vào Servlet**; Spring MVC sau đó tiếp tục ghép đường dẫn endpoint dựa trên `@RequestMapping`, `@GetMapping` và cấu hình MVC.

`"/"` là **default mapping** trong Servlet specification; `"/*"` là path-prefix mapping rộng hơn và có thể bắt cả những request vốn cần đi tới JSP hoặc Servlet khác. Đừng đổi hai giá trị này một cách tùy tiện.

### 3.2. Cấu hình Spring MVC với `@EnableWebMvc`

Tạo class `WebConfig` cùng package:

```java
package example.web;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackages = "example.web")
public class WebConfig {
}
```

- `@Configuration`: khai báo một class cấu hình bean Spring.
- `@EnableWebMvc`: bật cơ chế cấu hình MVC dựa trên Java, đăng ký các thành phần xử lý request phù hợp cho controller mapping, handler adapter và các chức năng MVC nền tảng.
- `@ComponentScan`: tìm controller/component trong package được chọn. Trong dự án lớn, giới hạn package quét đủ hẹp để không vô ý nạp quá nhiều bean.

Ở Spring Framework thuần, `@EnableWebMvc` là cách điển hình để cung cấp cấu hình MVC theo annotation. Trong **Spring Boot MVC**, nếu muốn giữ auto-configuration của Boot, thường **không** thêm `@EnableWebMvc` trừ khi chủ đích tự kiểm soát hoàn toàn cấu hình MVC.

### 3.3. Controller minh họa

```java
package example.web;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping(path = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "DispatcherServlet đã nhận yêu cầu";
    }
}
```

`@RestController` bao gồm ngữ nghĩa trả response body; `@GetMapping("/hello")` khai báo **mapping của handler bên trong Spring MVC**. Nội dung là text thuần, nên ví dụ không phụ thuộc một JSON serializer chỉ để trả chuỗi.

Khi WAR được triển khai dưới context path `/mvc-demo`, đường dẫn gọi thực tế là:

```text
http://localhost:8080/mvc-demo/hello
                     |       |
             context path    handler mapping
```

Đây là đường dẫn **bên ngoài ứng dụng**. Ở bên trong, mapping Servlet `"/"` hoạt động trên đường dẫn sau context path và Spring MVC ánh xạ `/hello`.

## 4. Ví dụ WAR hoàn chỉnh có thể triển khai

Các đoạn dưới đây cùng nhau tạo thành dự án Maven dùng **Spring Framework 6.2.0**, Jakarta Servlet 6.0 và Java 17. Các phiên bản này phục vụ một bài thực hành nhất quán, không có nghĩa bạn phải dùng phiên bản đó cho hệ thống đang vận hành.

### 4.1. Cấu trúc file

```text
mvc-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── web/
                    ├── WebAppInitializer.java
                    ├── WebConfig.java
                    └── HelloController.java
```

**Không tạo `src/main/webapp/WEB-INF/web.xml`** cho nhánh triển khai Java initializer này. Ba file Java dùng nguyên nội dung ở mục 3.

### 4.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>mvc-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.0</spring.version>
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

Các ý cần nhận biết:

- `spring-webmvc` cung cấp các thành phần Spring MVC, gồm `DispatcherServlet`; dependency transitively cung cấp phần nền tương ứng.
- `jakarta.servlet-api` là **provided** vì Tomcat cung cấp Servlet API khi chạy. Không đóng gói một Servlet API cạnh tranh trong WAR.
- `packaging=war` tạo archive mà Servlet container triển khai.
- `failOnMissingWebXml=false` thể hiện dụng ý không cần descriptor XML trong nhánh Java initializer.
- Mã nguồn dùng `jakarta.servlet.*`, không dùng `javax.servlet.*` như các dự án Servlet đời cũ.

Lưu ý Maven dùng cú pháp property `${spring.version}` trong XML thực tế. Nếu copy từ trình hiển thị làm xuất hiện ký tự `\` trước dấu `$`, hãy bỏ dấu gạch chéo đó; giá trị XML đúng là tên property Maven với cặp dấu `$` và ngoặc nhọn. 

### 4.3. Build, deploy và kiểm chứng

Điều kiện: JDK 17+, Maven và Tomcat 10.1 được cài đặt; Tomcat 10.1 sử dụng Jakarta Servlet 6.0. Tại thư mục dự án:

```bash
mvn clean package
```

Khi build thành công, Maven tạo `target/mvc-demo-1.0.0.war`. Sao chép WAR tới thư mục `webapps` của Tomcat với tên `mvc-demo.war` và chạy Tomcat. Ví dụ môi trường POSIX:

```bash
cp target/mvc-demo-1.0.0.war "$CATALINA_BASE/webapps/mvc-demo.war"
```

Nếu Tomcat dùng `CATALINA_HOME` làm thư mục triển khai và không đặt `CATALINA_BASE` riêng, thay bằng đường dẫn `webapps` thực tế. Trên Windows có thể copy file qua File Explorer. Tomcat cần cấu hình triển khai WAR và phải đang chạy; chỉ chạy `mvn package` không khởi động HTTP server.

Dùng:

```bash
curl --fail-with-body http://localhost:8080/mvc-demo/hello
```

Body trả về kỳ vọng:

```text
DispatcherServlet đã nhận yêu cầu
```

Cổng 8080, context path và host ở đây là **giả định của demo**; nếu tên WAR hoặc connector cấu hình khác, URL sẽ khác. `curl` có thể in response body không kèm một dòng newline, điều đó không đổi nội dung payload.

Đường đi khi chạy đúng:

```text
Tomcat tìm WebApplicationInitializer trong WAR
    -> WebAppInitializer.onStartup(...)
    -> tạo context từ WebConfig
    -> đăng ký DispatcherServlet với mapping "/"
    -> @ComponentScan tìm HelloController
    -> GET /mvc-demo/hello
    -> DispatcherServlet chọn HelloController.hello()
    -> HTTP 200, body text/plain
```

Nếu muốn tự xác minh class nào tham gia, kiểm tra danh sách Servlet registrations lúc startup và log khởi tạo `DispatcherServlet` trên Tomcat. Đừng dùng việc package thành công làm bằng chứng rằng HTTP endpoint đã chạy.

## 5. Cách viết trực tiếp `WebApplicationInitializer`

Thừa kế `AbstractAnnotationConfigDispatcherServletInitializer` tiện lợi nhưng đôi khi cần thấy chính xác Spring giao tiếp với Servlet container thế nào. Lựa chọn tương đương là tự triển khai `org.springframework.web.WebApplicationInitializer`:

```java
package example.web;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.WebApplicationInitializer;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;

public class ManualInitializer implements WebApplicationInitializer {

    @Override
    public void onStartup(ServletContext servletContext)
            throws ServletException {

        AnnotationConfigWebApplicationContext context =
                new AnnotationConfigWebApplicationContext();
        context.register(WebConfig.class);

        DispatcherServlet dispatcher = new DispatcherServlet(context);

        ServletRegistration.Dynamic registration =
                servletContext.addServlet("mvc", dispatcher);
        if (registration == null) {
            throw new ServletException("Tên Servlet 'mvc' đã được sử dụng");
        }

        registration.setLoadOnStartup(1);
        registration.addMapping("/");
    }
}
```

Ý nghĩa từng thao tác:

1. Tạo `AnnotationConfigWebApplicationContext`: Spring context lấy cấu hình từ annotation/Java class.
2. `context.register(WebConfig.class)`: đăng ký nguồn cấu hình MVC. Context sẽ được refresh trong vòng đời do dispatcher quản lý khi khởi tạo.
3. `new DispatcherServlet(context)`: liên kết dispatcher với Spring context.
4. `servletContext.addServlet("mvc", dispatcher)`: yêu cầu **Servlet container** đăng ký Servlet có tên `mvc`; trả về đối tượng cấu hình động.
5. `setLoadOnStartup(1)`: đặt thứ tự ưu tiên tải/khởi tạo khi ứng dụng khởi động, thay vì mặc định đợi request đầu tiên.
6. `addMapping("/")`: đăng ký URL pattern ở lớp Servlet.

**Đây là một phương án thay thế `WebAppInitializer` của mục 3.** Để chạy cách này, **xóa/loại khỏi WAR class `WebAppInitializer` cũ**, đổi `ManualInitializer.java` thành file có nội dung trên, giữ `WebConfig` và `HelloController`. Không deploy đồng thời cả hai initializer cùng đăng ký mapping `"/"`; tên khác nhau không khiến hai Servlet trở thành hai front controller hợp lệ cho cùng một URL pattern.

Java Servlet registration có thể cấu hình thêm init-params, async support và multipart config khi bài toán cần. Ví dụ này tập trung vào luồng khởi tạo tối thiểu.

## 6. Nhận biết `WEB-INF/web.xml` truyền thống

### 6.1. Vị trí và vai trò

`web.xml` là **deployment descriptor** của ứng dụng Servlet. Với WAR, nó nằm tại:

```text
src/main/webapp/WEB-INF/web.xml
          |
          v (sau khi đóng gói)
WEB-INF/web.xml trong WAR
```

Descriptor này khai báo Servlet, Servlet mapping, Filter, Listener, init-params, security constraints và một số cấu hình Servlet container khác. Nó được **Servlet container** đọc, không phải một file Spring bean XML thuần.

### 6.2. `web.xml` tương ứng với ví dụ Java trên

Để triển khai **cùng `WebConfig` và `HelloController` nhưng bằng XML**, loại bỏ class `WebAppInitializer`/`ManualInitializer` trong WAR rồi thêm `src/main/webapp/WEB-INF/web.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <servlet>
        <servlet-name>mvc</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>

        <init-param>
            <param-name>contextClass</param-name>
            <param-value>
                org.springframework.web.context.support.AnnotationConfigWebApplicationContext
            </param-value>
        </init-param>

        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>example.web.WebConfig</param-value>
        </init-param>

        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>mvc</servlet-name>
        <url-pattern>/</url-pattern>
    </servlet-mapping>
</web-app>
```

Đây là **XML descriptor cho Servlet 6.0/Jakarta**, không dùng URI schema Java EE/`javax.servlet` cũ. Sau khi deploy như ở mục 4, endpoint vẫn là `GET /mvc-demo/hello`.

Đọc từng thẻ:

| Thành phần XML | Tác dụng | Tương ứng ở Java |
| --- | --- | --- |
| `<servlet>` | Khai báo một Servlet cho container | `servletContext.addServlet(...)` |
| `<servlet-name>mvc</servlet-name>` | Định danh Servlet, liên kết với mapping | Tên `"mvc"` trong `addServlet` |
| `<servlet-class>...DispatcherServlet</servlet-class>` | Chỉ định class Servlet cần tạo | `new DispatcherServlet(context)` |
| `<init-param>contextClass</init-param>` | Dùng `AnnotationConfigWebApplicationContext` thay context XML mặc định | `new AnnotationConfigWebApplicationContext()` |
| `<init-param>contextConfigLocation</init-param>` | Chỉ tới `example.web.WebConfig`, **tên class cấu hình** khi dùng context dạng annotation | `context.register(WebConfig.class)` |
| `<load-on-startup>1</load-on-startup>` | Khởi tạo sớm khi deploy | `registration.setLoadOnStartup(1)` |
| `<servlet-mapping>` và `<url-pattern>/</url-pattern>` | Đăng ký URL pattern | `registration.addMapping("/")` |

**Không nhầm lẫn:** `contextConfigLocation` là một **tên init-param** của Spring. Ý nghĩa giá trị phụ thuộc `contextClass`. Với `XmlWebApplicationContext`, giá trị có thể là đường dẫn bean XML; với `AnnotationConfigWebApplicationContext` trong ví dụ là class `@Configuration`.

### 6.3. Nhận biết XML truyền thống hơn

Trong codebase cũ, bạn có thể gặp cấu hình này:

```xml
<servlet>
    <servlet-name>dispatcher</servlet-name>
    <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
    <init-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>/WEB-INF/spring/mvc-config.xml</param-value>
    </init-param>
    <load-on-startup>1</load-on-startup>
</servlet>
<servlet-mapping>
    <servlet-name>dispatcher</servlet-name>
    <url-pattern>/</url-pattern>
</servlet-mapping>
```

Đây là **một fragment bên trong `web.xml` hợp lệ**, không phải toàn bộ file độc lập. Nó tham chiếu tới **Spring bean XML** `/WEB-INF/spring/mvc-config.xml`, file khác với descriptor `web.xml`. Khi không khai báo `contextClass` và sử dụng cấu hình Servlet mặc định của `DispatcherServlet`, Spring thường dùng `XmlWebApplicationContext`.

Nhiều dự án còn không ghi `contextConfigLocation`: khi đó `DispatcherServlet` có quy ước tìm một file mặc định theo `servlet-name`, ví dụ `/WEB-INF/dispatcher-servlet.xml`. Không nên đoán rằng mọi dự án đều dùng đường dẫn mặc định; hãy đọc `init-param` và cấu hình context thực tế.

Nếu muốn dùng XML bean configuration, nội dung file `mvc-config.xml` thường đăng ký controller scanning và khả năng annotation MVC qua các phần tử tương ứng như `<context:component-scan>` và `<mvc:annotation-driven>`. Những phần tử này thuộc **Spring bean XML**, không phải thẻ của Servlet descriptor.

### 6.4. Khi nào vẫn thấy `web.xml`?

- Ứng dụng Servlet/Spring MVC cũ chưa chuyển sang Java initializer.
- Nhóm dự án duy trì quy ước deployment descriptor cho nhiều Servlet, Filter, Listener.
- Hệ thống muốn dùng kết hợp descriptor và một số registration lập trình có kiểm soát.

**Không phải:** thiếu `web.xml` luôn là lỗi cấu hình. Với container và WAR phù hợp, Java initializer có thể đăng ký hoàn toàn bằng code. Maven WAR plugin có thể cần cấu hình rõ mục đích không yêu cầu descriptor, như mục 4.

## 7. Hai loại Spring application context

Ở hệ thống MVC lớn có thể tồn tại **root WebApplicationContext** và một hoặc nhiều **child WebApplicationContext** dành cho từng `DispatcherServlet`:

```text
ServletContext (toàn bộ web application)
  |
  +-- Root WebApplicationContext
  |      ├── services
  |      ├── repositories
  |      └── shared infrastructure
  |
  +-- DispatcherServlet "mvc"
            |
            +-- Child WebApplicationContext
                  ├── controllers
                  ├── HandlerMappings
                  ├── HandlerAdapters
                  └── view resolvers / MVC config
```

Trong ví dụ đơn giản, `getRootConfigClasses()` trả `null`, Spring MVC configuration nằm trong context dành cho dispatcher. Nếu muốn tách lớp business và MVC configuration, có thể viết:

```java
@Override
protected Class<?>[] getRootConfigClasses() {
    return new Class<?>[] { RootConfig.class };
}

@Override
protected Class<?>[] getServletConfigClasses() {
    return new Class<?>[] { WebConfig.class };
}
```

Đây chỉ là **fragment minh họa**: ứng dụng muốn chạy phải định nghĩa `RootConfig` và giới hạn component scan phù hợp. Trong context hierarchy, bean trong child thường nhìn thấy bean từ parent; chiều ngược lại **không tự động**. Nếu quét một controller vào root context thay vì servlet context, servlet context con có thể không đăng ký handler mapping như dự kiến.

Dạng `web.xml` tương ứng thường có `ContextLoaderListener` để khởi tạo root context; cấu hình root qua `<context-param>`, còn dispatcher child qua `<servlet><init-param>...`. Đây là **hai phạm vi cấu hình** dù dùng cùng tên `contextConfigLocation`. Không mặc định thêm `ContextLoaderListener` nếu ứng dụng không cần root context riêng.

## 8. Java initializer và `web.xml`: đối chiếu vai trò

| Góc nhìn | Java initializer | `web.xml` |
| --- | --- | --- |
| Nơi khai báo | Java class trong WAR, implements `WebApplicationInitializer` | `WEB-INF/web.xml` |
| Cơ chế container kích hoạt | Phát hiện `ServletContainerInitializer` rồi gọi `onStartup` | Container phân tích deployment descriptor |
| Cấu hình `DispatcherServlet` | `addServlet(...)` hoặc abstract initializer | `<servlet>` + `<servlet-class>` |
| URL mapping | `addMapping("/")` hoặc `getServletMappings()` | `<servlet-mapping><url-pattern>/</url-pattern>` |
| Init-param | `registration.setInitParameter(...)` hoặc logic trong context | `<init-param>` |
| Nạp sớm | `setLoadOnStartup(1)` | `<load-on-startup>1</load-on-startup>` |
| Spring Java configuration | `WebConfig.class` | `AnnotationConfigWebApplicationContext` + class name |
| Root context khi cần | `getRootConfigClasses()` | `ContextLoaderListener` cùng root context config |
| Phù hợp | Dự án Java config trên Servlet stack | Hệ thống legacy hoặc descriptor-centric |

Hai phương pháp đều dẫn tới **một `DispatcherServlet` được Servlet container quản lý**. Java initializer cũng không có nghĩa bỏ qua Servlet specification: nó sử dụng chính API động của specification đó.

## 9. Spring Boot khởi tạo khác như thế nào?

Với Spring Boot Web MVC có embedded Servlet container, điểm vào thường là `@SpringBootApplication` và `SpringApplication.run(...)`. Boot tự thiết lập nhiều phần của servlet web server, context, dispatcher registration và cấu hình MVC dựa trên các điều kiện classpath/bean/property.

Ví dụ **chỉ để nhận diện phong cách Boot**, độc lập với WAR Framework thuần ở mục 4:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

- Với `spring-boot-starter-web`, ứng dụng điển hình không cần tự viết `WebAppInitializer` hoặc `web.xml`.
- Trong Boot, có thể dùng `ServletRegistrationBean` hoặc `FilterRegistrationBean` khi thật sự phải tự khai báo Servlet/Filter riêng; cách này thuộc **Spring Boot API**, không giống triển khai `WebApplicationInitializer` cho WAR Spring Framework thuần.
- Khi đóng gói WAR để đưa vào Servlet container bên ngoài, Boot có workflow thích hợp (chẳng hạn `SpringBootServletInitializer`) và phụ thuộc container theo scope phù hợp. Đừng lấy bộ ba class Framework thuần trong bài rồi giả định đó là cấu hình mặc định cho Boot executable JAR.
- Spring WebFlux sử dụng cơ chế HTTP dispatch reactive; đừng áp dụng `DispatcherServlet` cho server WebFlux thuần.

## 10. Lỗi thường gặp và cách xác minh

### 10.1. Lỗi 404 dù đã viết `@GetMapping`

Kiểm tra theo thứ tự:

1. Đúng host/port và **context path** của WAR chưa? `/mvc-demo/hello` khác `/hello` khi deploy dưới tên `mvc-demo.war`.
2. WAR đã triển khai thành công và container thực sự phát hiện `WebAppInitializer` chưa?
3. Có mapping `"/"` cho đúng `DispatcherServlet` không?
4. `WebConfig` có `@EnableWebMvc` và `@ComponentScan` bao gồm package controller không?
5. `@GetMapping` có đúng đường dẫn và HTTP method không?
6. Có Servlet khác chiếm mapping hoặc filter/security chặn request không?

Nếu bạn gọi `GET /mvc-demo/hello` mà nhận 404, phải xác định 404 từ **Tomcat trước khi vào Spring** hay từ **Spring MVC sau khi không tìm ra handler**; startup log, mapping registration và request log giúp phân biệt.

### 10.2. Ứng dụng không phát hiện initializer

Các nguyên nhân có thể xảy ra:

- Class initializer không nằm trong WAR `WEB-INF/classes` hoặc không được quét.
- Class không implement `WebApplicationInitializer` / không extends initializer trừu tượng.
- Dependency Spring MVC không được đóng gói phù hợp hoặc cơ chế container initializer bị hạn chế bởi cấu hình deployment.
- Dùng sai Servlet container / namespace `javax` versus `jakarta`.
- Có lỗi khởi tạo bean/Servlet khác khiến startup thất bại; xem **lỗi gốc đầu tiên** trong server log.

Kiểm tra nội dung WAR bằng công cụ JDK:

```bash
jar tf target/mvc-demo-1.0.0.war
```

Bạn cần thấy ít nhất class `WEB-INF/classes/example/web/WebAppInitializer.class` và các JAR Spring liên quan trong `WEB-INF/lib`. Kiểm tra theo đường dẫn class thực tế, không dựa vào tên file Java trên máy phát triển.

### 10.3. Lỗi trùng `DispatcherServlet` hoặc xung đột mapping

Thường do giữ cả `web.xml` và Java initializer đăng ký cùng URL, hoặc để nhiều initializer cùng tồn tại. Việc Servlet container cho phép cấu hình Java kết hợp XML **không có nghĩa cứ đăng ký trùng là hợp lệ**. Hãy xác định duy nhất cơ chế sở hữu mỗi Servlet name/mapping và loại bỏ khai báo chồng chéo.

### 10.4. Sai `contextConfigLocation`

- Trong `web.xml` mặc định XML context: giá trị kiểu `/WEB-INF/mvc-config.xml` là đường dẫn tới **Spring bean configuration XML**.
- Trong `web.xml` chọn `AnnotationConfigWebApplicationContext`: giá trị `example.web.WebConfig` là **tên class cấu hình**.
- Trong Java initializer: `getServletConfigClasses()` thường trả **Class<?>[]**, không phải tên file XML.
- `getRootConfigClasses()` và `getServletConfigClasses()` trộn sai package scan có thể dẫn tới không tìm thấy controller hoặc bean lặp.

### 10.5. Trộn các thế hệ `javax` và `jakarta`

Spring Framework 6 và Tomcat 10.1 làm việc với Jakarta Servlet; các ứng dụng Spring MVC 5/Tomcat 9 thường thuộc họ `javax.servlet.*`. Nếu đổi namespace một nửa, lỗi có thể là `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` hoặc Servlet không khởi tạo. Đồng bộ framework, dependency, container và import source code; **không chữa bằng cách thêm song song hai Servlet API cạnh tranh**.

### 10.6. Dùng `@EnableWebMvc` sai bối cảnh

Trong Framework thuần, `@EnableWebMvc` là cách phổ biến để thiết lập Java MVC configuration. Trong Spring Boot, nó có thể vô hiệu hóa một số cơ chế MVC auto-configuration mà Boot tự cung cấp. Xem dự án là **WAR Framework thuần hay Boot** trước khi copy code.

## 11. Thực hành tự kiểm tra

**Bài 1 — xác định lớp mapping:** Cho `getServletMappings() = new String[]{"/api/*"}` và controller có `@GetMapping("/hello")`, WAR chạy tại context path `/mvc-demo`. Request thường có dạng `GET /mvc-demo/api/hello`. Vì `/api/*` là mapping Servlet, tiền tố `/api` là phần đường dẫn Servlet; còn `/hello` là mapping controller tương ứng. Hãy giải thích vì sao gọi `/mvc-demo/hello` không chạm tới dispatcher đó.

**Bài 2 — chuyển đổi cấu hình:** Từ Java `getServletMappings() = new String[]{"/"}`, `getServletConfigClasses() = {WebConfig.class}`, `getRootConfigClasses() = null`, viết descriptor `web.xml` khai báo `DispatcherServlet`, `contextClass` và `contextConfigLocation` sao cho không cần root context. So lại với bảng ở mục 6.2.

**Bài 3 — chẩn đoán lỗi:** WAR có controller và `WebConfig`, nhưng servlet container không log việc đăng ký dispatcher. Nêu ba điều cần kiểm tra trước khi sửa `@GetMapping`: class initializer trong WAR, cơ chế discovery, và compatibility Servlet/Spring.

**Bài 4 — thiết kế context:** Nếu có hai `DispatcherServlet` riêng, mỗi servlet có controller khác nhau nhưng dùng chung service, hãy mô tả việc đặt service vào root context và MVC infrastructure vào servlet context con. Phân biệt khi nào cần `ContextLoaderListener`.

### Câu hỏi ghi nhớ

- **`DispatcherServlet` do ai đăng ký?** Servlet container nhận declaration từ `web.xml` hoặc Java registration do `WebApplicationInitializer` thực hiện.
- **`WebApplicationInitializer` là gì?** SPI Spring được tự động phát hiện qua cơ chế initializer của Servlet container để cấu hình `ServletContext` lập trình.
- **`@EnableWebMvc` có thay cho `addServlet` không?** Không. Nó cấu hình các bean MVC; vẫn cần Servlet container biết `DispatcherServlet`.
- **Có bắt buộc `web.xml` không?** Không, nếu Java registration và các điều kiện startup của Servlet container được đáp ứng.
- **`contextConfigLocation` có luôn chỉ tới XML không?** Không; với `AnnotationConfigWebApplicationContext` nó có thể chỉ tới Java `@Configuration` class.
- **Một ứng dụng Boot với `spring-boot-starter-web` có thường cần Java initializer trong bài không?** Không. Boot cung cấp quy trình bootstrap/auto-configuration riêng.

## 12. Tham khảo chính thức

- DispatcherServlet và cấu hình Java/XML: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html
- Servlet Config, `WebApplicationInitializer`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/container-config.html
- Context hierarchy: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/context-hierarchy.html
- Cấu hình Spring MVC bằng Java: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/config.html
- `WebApplicationInitializer` API: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/WebApplicationInitializer.html

**Cần nhớ:** `web.xml` và `WebApplicationInitializer` đều giúp Servlet container biết `DispatcherServlet` tồn tại và xử lý URL nào. Spring `WebConfig` quyết định **dispatcher sẽ tìm các MVC bean/controller bằng cách nào**. Hai tầng trách nhiệm này cần được hiểu tách biệt khi khởi tạo và gỡ lỗi Spring MVC.
