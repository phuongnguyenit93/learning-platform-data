# Giới hạn JSP theo máy chủ và kiểu đóng gói

Trong Spring Boot, một ứng dụng web có thể trả HTML từ **JSP (Jakarta Server Pages)** qua Spring MVC. Tuy nhiên, JSP không có mức hỗ trợ giống nhau trên mọi Servlet container và mọi kiểu artifact. Đặc biệt, một ứng dụng có thể chạy được trong IDE, mở trang JSP khi chạy bằng Maven, nhưng lại không tìm thấy hoặc không biên dịch được JSP sau khi đóng gói thành **executable JAR**. Đây là vấn đề của **JSP engine, cơ chế ServletContext và bố cục artifact**, không đơn thuần là lỗi view resolver.

Bài học sử dụng **Spring Boot 3.3.x, Java 17+, Spring MVC Servlet** làm mốc minh họa. Khi nâng cấp major version hoặc đổi container, cần kiểm tra tài liệu tương ứng. Trọng tâm là hiểu ma trận hỗ trợ JSP theo **Tomcat / Jetty / Undertow**, **executable JAR / executable WAR / WAR triển khai ngoài**, từ đó chọn cấu trúc project và quy trình kiểm thử hợp lý.

## 1. Kết quả học tập

Sau bài này, bạn cần:

1. Giải thích JSP được biên dịch và thực thi như một **Servlet** ra sao, và Spring MVC chuyển từ **logical view name** đến file JSP thế nào.
2. Chỉ ra giới hạn chính thức: **Tomcat/Jetty + WAR** là hướng hỗ trợ JSP trong embedded setup, **executable JAR không hỗ trợ JSP**, còn **Undertow không hỗ trợ JSP**.
3. Phân biệt **executable WAR chạy bằng java -jar** với **WAR triển khai vào Servlet container bên ngoài**; hiểu vai trò của **SpringBootServletInitializer** và dependency scope **provided**.
4. Đặt JSP đúng nơi (**src/main/webapp/WEB-INF/jsp/**), cấu hình view prefix/suffix, khai báo JSP compiler/JSTL theo namespace **jakarta** của Spring Boot 3.x.
5. Tạo được ứng dụng tối thiểu với một JSP view và một REST endpoint, build WAR rồi kiểm tra cả HTML lẫn JSON qua HTTP thực.
6. Nhận biết lỗi khi dùng JAR, thiếu Jasper, sai đường dẫn, lệch javax/jakarta, view resolver sai, servlet container không hỗ trợ JSP và cấu hình error page không phù hợp.
7. Chọn công nghệ render khác như Thymeleaf khi yêu cầu triển khai ưu tiên executable JAR, container linh hoạt hoặc frontend tách riêng.

**Ranh giới:** đây là bài về **khả năng JSP chạy theo server và kiểu đóng gói**. Không đi sâu cú pháp scriptlet, thiết kế giao diện, quản lý phiên đăng nhập hay tối ưu template engine.

## 2. JSP là gì trong một Spring MVC web application?

JSP là công nghệ **server-side view** của hệ Servlet. Một JSP được JSP engine (ví dụ **Apache Jasper** của Tomcat) chuyển thành mã Servlet, biên dịch khi cần rồi thực thi để tạo HTML. Browser không chạy JSP; browser chỉ nhận response HTML cuối cùng.

Luồng điển hình:

~~~text
Browser: GET /ui/hello
       |
       v
Servlet container (Tomcat/Jetty có JSP engine thích hợp)
       |
       v
DispatcherServlet
       |
       v
@Controller @GetMapping("/ui/hello")
       |
       +-- model.addAttribute("greeting", ...)
       +-- return "hello" (logical view name)
       |
       v
InternalResourceViewResolver
       |
       +-- prefix = /WEB-INF/jsp/
       +-- suffix = .jsp
       v
/WEB-INF/jsp/hello.jsp
       |
       v
JSP engine biên dịch/thực thi JSP
       |
       v
HTTP 200 text/html + HTML body
~~~

Ở Spring MVC, **@Controller** cùng phương thức trả **String** thường chọn tên view; **@RestController** (hoặc @ResponseBody) trả dữ liệu trực tiếp trong body, không chọn JSP. Vì vậy, đổi @Controller thành @RestController rồi trả "hello" có thể khiến trình duyệt chỉ thấy chữ **hello**, hoàn toàn không render JSP.

**InternalResourceViewResolver** chuyển tên view "hello" sang đường dẫn Servlet resource **/WEB-INF/jsp/hello.jsp**. Đây là bước lựa chọn view; nó **không tự cài đặt JSP compiler**. Servlet container phải có cơ chế JSP tương thích để xử lý file JSP. Controller, view resolver, JSP engine và WAR packaging là những mắt xích khác nhau.

JSP nên nằm trong **WEB-INF**: Servlet container không cho HTTP client truy cập trực tiếp file dưới WEB-INF, trong khi controller có thể forward tới đó để render. Đặt JSP ngoài WEB-INF có thể làm file bị truy cập trực tiếp ngoài luồng controller hoặc tạo đường dẫn UI khó kiểm soát.

## 3. Ma trận hỗ trợ theo server và packaging

Đối với **Spring Boot 3.3 embedded Servlet container khi đóng gói executable archive**, tài liệu Spring Boot xác nhận:

| Servlet server | Executable JAR (java -jar file.jar) | Executable WAR (java -jar file.war) | WAR triển khai vào container ngoài |
| --- | --- | --- | --- |
| **Tomcat** | **Không hỗ trợ JSP** | **Có thể dùng JSP** khi có Jasper/Jakarta dependency đúng và JSP ở WAR webapp | **Có thể dùng**, nếu external Tomcat và WAR tương thích Servlet/Jakarta |
| **Jetty** | **Không hỗ trợ JSP** | **Có thể dùng JSP**, cần cấu hình JSP engine/module và phiên bản Jetty tương thích | **Có thể dùng**, nếu Jetty ngoài cung cấp JSP và phù hợp WAR |
| **Undertow** | **Không hỗ trợ JSP** | **Không hỗ trợ JSP** theo Spring Boot | Không xem đây là mục tiêu JSP được bảo đảm; cần container JSP-capable khác |
| **Container Servlet khác** | Không áp dụng kết luận JAR cho mọi kỹ thuật tùy biến | Phụ thuộc server/runtime; không tự suy ra được hỗ trợ | Chỉ phù hợp khi container hỗ trợ Servlet/Jakarta, JSP engine và môi trường tương ứng |

**Cách đọc ma trận:**

- Cột **executable JAR** nói về **cách đóng gói ứng dụng Spring Boot**. Dù JAR chứa embedded Tomcat và controller hoạt động, **JSP không được Spring Boot hỗ trợ trong executable JAR**. Thêm Jasper mà giữ packaging JAR không giải quyết được giới hạn này.
- Cột **executable WAR** là WAR do Spring Boot build plugin đóng gói để vừa chạy bằng **java -jar**, vừa có thể triển khai vào container bên ngoài. **WAR không đồng nghĩa bắt buộc phải cài Tomcat riêng**.
- Cột **external WAR** là WAR do container bên ngoài nạp. Servlet/JSP implementation và cấu hình deployment nằm một phần ở container đó; có thể cần kiểm tra phiên bản và module JSP.
- **Undertow không hỗ trợ JSP** theo hướng dẫn JSP limitations của Spring Boot. Không đổi sang Undertow chỉ để tiết kiệm tài nguyên nếu đang có requirement JSP.
- Với **Jetty**, tài liệu nói **should work** với WAR, không có nghĩa mọi cấu hình mặc định đã có JSP engine. Cần xác minh cách tích hợp JSP, class loader và phiên bản Jetty thực tế trước khi cam kết chạy production.

**Quy tắc quyết định nhanh:** nếu dự án bắt buộc dùng JSP và muốn Spring Boot nhúng container, hãy chọn **Tomcat + WAR** làm phương án thực hành rõ ràng nhất. Nếu artifact bắt buộc là **JAR**, hãy chọn công nghệ view không cần JSP thay vì tìm cách ép JSP vào executable JAR.

## 4. JAR và WAR khác nhau vì sao?

### 4.1. Executable JAR

Một Spring Boot executable JAR thường có bố cục như:

~~~text
application.jar
  META-INF/
  BOOT-INF/
    classes/
      com/example/...class
      application.yml
      static/
      templates/
    lib/
      spring-*.jar
      tomcat-*.jar
      ...
  org/springframework/boot/loader/...
~~~

JAR phù hợp cho Spring MVC REST API, static content trong **src/main/resources/static/** và các template engine như Thymeleaf trong **src/main/resources/templates/**. Tuy nhiên, JSP muốn dùng ServletContext web resource và cơ chế JSP engine vốn được thiết kế theo bố cục web application. Spring Boot **không hỗ trợ JSP với executable JAR**. Không suy luận rằng cứ nằm trong BOOT-INF/classes thì JSP được xem là JSP resource.

Trong thực tế **src/main/webapp/** không phải thư mục đáng tin cậy của executable JAR; tài liệu Spring Boot cảnh báo nó thường bị build tool bỏ qua khi tạo JAR. Đây là lý do một project JSP có thể chạy trong IDE nhưng hỏng sau **java -jar app.jar**.

### 4.2. WAR truyền thống

WAR là định dạng web application của Java Servlet. Bố cục thường gồm:

~~~text
application.war
  WEB-INF/
    classes/
      com/example/...class
      application.yml
    lib/
      spring-*.jar
      ...
    jsp/
      hello.jsp
  META-INF/
  ...
~~~

**WEB-INF/jsp/hello.jsp** là Servlet resource trong WAR và có thể được JSP engine của container xử lý khi Spring MVC forward đến. File JSP nằm đúng vị trí **webapp** của WAR, khác với template trong classpath:/templates.

Nếu deploy lên external Tomcat, Tomcat cung cấp Servlet/JSP container, còn ứng dụng mang controller, service và view. Tên WAR hoặc cấu hình container thường quyết định **context path**: WAR **demo.war** có thể được truy cập dưới **/demo/ui/hello**, trong khi executable WAR chạy bằng java -jar thường dùng context path **/** nếu chưa đổi **server.servlet.context-path**. Không hardcode URL bên ngoài mà bỏ qua context path/proxy.

### 4.3. Executable WAR và WEB-INF/lib-provided

Spring Boot Maven/Gradle plugin có thể biến WAR thành **executable WAR**. Để vừa chạy nhúng container vừa deploy ngoài, dependency runtime thuộc container nên khai báo **provided** (Maven) hoặc **providedRuntime** (Gradle) theo hướng dẫn Spring Boot.

Trong executable WAR, plugin có thể đặt dependency dạng provided vào **WEB-INF/lib-provided/**. Khi chạy **java -jar application.war**, Boot loader có thể sử dụng chúng; khi WAR được deploy vào container ngoài, chúng không được đưa vào classpath webapp như các JAR thuộc **WEB-INF/lib**, tránh chồng chéo với servlet engine/container bên ngoài.

Ví dụ sơ đồ:

~~~text
application.war
  WEB-INF/
    classes/
    jsp/
      hello.jsp
    lib/
      spring-webmvc-*.jar
      ...
    lib-provided/
      tomcat-embed-*.jar
      tomcat-embed-jasper-*.jar
      ...
  org/springframework/boot/loader/...
~~~

Đây là sơ đồ, không phải danh sách chính xác của mọi artifact. **Kiểm tra artifact build thật** để biết dependency có nằm đúng nơi, nhất là khi thay container hoặc chỉnh plugin packaging.

**Đừng nhầm:** WAR thông thường chưa chắc có main/Boot launcher để chạy bằng java -jar; “WAR” và “executable WAR” là hai thuộc tính khác nhau. Spring Boot build plugin được cấu hình đúng mới tạo artifact có khả năng vừa chạy standalone vừa deploy ngoài.

## 5. Tại sao JSP phụ thuộc vào Servlet container?

### 5.1. Jasper và JSP engine

Tomcat hỗ trợ JSP qua engine **Jasper**. Spring MVC chỉ chuẩn bị model, view name, forward; Jasper xử lý JSP syntax, expression language, tag library và biên dịch JSP thành Servlet khi cần. Nếu thiếu JSP compiler/runtime, ứng dụng có thể khởi động, API JSON vẫn chạy nhưng request tới JSP gặp **404**, **500** hoặc thông báo compilation/servlet exception.

Với Tomcat nhúng, artifact thường cần dependency **org.apache.tomcat.embed:tomcat-embed-jasper**. Cần chọn phiên bản do Spring Boot BOM quản lý để tránh lệch Tomcat core và JSP engine. Không kéo ngẫu nhiên **tomcat-jasper** của một phiên bản Tomcat khác vào ứng dụng có embedded Tomcat 10.1.

### 5.2. Jetty

Jetty có cách cung cấp JSP implementation/module riêng, tùy dòng Jetty và môi trường EE được bật. Spring Boot cho biết JSP có thể dùng với Jetty khi đóng gói WAR, nhưng dependency/module JSP phải tương thích và được khởi tạo đúng. Đừng lấy dependency Jasper dành cho embedded Tomcat rồi giả định nó là lựa chọn chuẩn cho Jetty.

Nếu chuyển Tomcat sang Jetty, hãy kiểm chứng **JSP rendering trên WAR đã package**, không chỉ kiểm tra startup hoặc API trả 200. Một Jetty deployment muốn chạy JSP cần JSP-capable configuration thực tế.

### 5.3. Undertow

Theo hướng dẫn Spring Boot về JSP limitations, **Undertow không hỗ trợ JSP**. Dùng Undertow cho REST API hoặc ứng dụng không cần JSP là câu chuyện khác; không coi việc đổi dependency Undertow và giữ nguyên JSP là con đường migration được hỗ trợ.

### 5.4. Servlet và Jakarta EE version

Spring Boot 3.x sử dụng **jakarta.\*** thay cho **javax.\*** trong Jakarta EE APIs. Spring Boot 3.3 làm việc với thế hệ Servlet container hỗ trợ Jakarta, ví dụ Tomcat 10.1. WAR dùng Spring Boot 3.3 không nên deploy vào **Tomcat 9** cũ (dùng javax.servlet) rồi trông chờ JSP tự dịch được. Chọn container theo version, Servlet/JSP API, Java runtime và dependency management.

Lỗi **NoClassDefFoundError: javax/servlet/...**, **ClassNotFoundException: jakarta/servlet/...**, lỗi taglib hay TLD có thể báo hiệu trộn thư viện cũ và mới. Không khắc phục bằng cách đưa đồng thời mọi bản **javax.servlet** và **jakarta.servlet** vào WAR. Hãy thống nhất một dòng Servlet/Jakarta tương thích với Spring Boot target.

## 6. Thực hành đầy đủ: Spring Boot 3.3 + Tomcat + executable WAR + JSP

Ví dụ cố định mốc **Spring Boot 3.3.13**, **Java 17**, **Maven**, **Spring MVC**, **embedded Tomcat** để thấy rõ cấu hình WAR. Khi dùng sản phẩm thực tế, chọn bản patch được hỗ trợ và áp dụng quy trình cập nhật bảo mật của dự án. Dùng **Maven wrapper** do Spring Initializr tạo cùng project nếu có.

Ứng dụng có:

- **GET /ui/hello** → Spring MVC controller trả logical view **hello**; JSP render HTML.
- **GET /api/status** → REST endpoint trả JSON, không dùng JSP.
- **GET /WEB-INF/jsp/hello.jsp** → không được truy cập trực tiếp qua HTTP.

### 6.1. Cấu trúc project

~~~text
jsp-war/
  pom.xml
  mvnw
  mvnw.cmd
  src/
    main/
      java/com/example/jspwar/
        JspWarApplication.java
        PageController.java
        ApiController.java
      resources/
        application.properties
      webapp/
        WEB-INF/
          jsp/
            hello.jsp
    test/
      java/com/example/jspwar/
        PageControllerTest.java
~~~

**src/main/webapp/WEB-INF/jsp/** là vị trí quan trọng. Không chuyển file JSP mẫu sang **src/main/resources/templates/** rồi kỳ vọng view resolver Servlet tự biên dịch nó. Thư mục templates thường dành cho Thymeleaf/FreeMarker/Mustache, không tương đương Servlet WAR webapp root.

### 6.2. pom.xml hoàn chỉnh

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
    <artifactId>jsp-war</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.apache.tomcat.embed</groupId>
            <artifactId>tomcat-embed-jasper</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>jakarta.servlet.jsp.jstl</groupId>
            <artifactId>jakarta.servlet.jsp.jstl-api</artifactId>
        </dependency>

        <dependency>
            <groupId>org.glassfish.web</groupId>
            <artifactId>jakarta.servlet.jsp.jstl</artifactId>
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

**Giải thích dependency:**

1. **spring-boot-starter-web** đưa Spring MVC và embedded Tomcat starter vào ứng dụng.
2. Khai báo trực tiếp **spring-boot-starter-tomcat** với **provided** để khi deploy WAR ngoài, Servlet container không bị lẫn thư viện embedded. Dù starter-web có Tomcat transitively, khai báo trực tiếp scope provided là pattern trong hướng dẫn WAR của Spring Boot.
3. **tomcat-embed-jasper** là JSP compiler/runtime phục vụ Tomcat nhúng. Scope **provided** giúp Boot đóng gói đúng với executable/deployable WAR, đồng thời external Tomcat dùng JSP engine của container. Không hardcode version Jasper khác version Tomcat do Boot quản lý.
4. **jakarta.servlet.jsp.jstl-api** và **org.glassfish.web:jakarta.servlet.jsp.jstl** hỗ trợ tag library JSTL theo Jakarta. Spring Boot 3.3 BOM quản lý version của các artifact này.
5. **spring-boot-maven-plugin** repackages WAR thành executable WAR. Với WAR mà không được repackage, **java -jar** có thể không chạy như Spring Boot executable artifact.
6. **spring-boot-starter-test** cho unit test/controller test; **không** chứng minh JSP compiler làm việc bên trong WAR nếu chỉ chạy test Java.

Nếu JSP hoàn toàn không dùng JSTL, hai dependency JSTL có thể không cần thiết, nhưng ví dụ dùng **c:out** để HTML-escape dữ liệu. Spring Boot 3.x sử dụng **Jakarta Tags 3.0** URI **jakarta.tags.core**, không sao chép vô điều kiện tag URI của project Spring Boot 1.x/2.x.

### 6.3. Ứng dụng có thể chạy standalone hoặc deploy WAR ngoài

**src/main/java/com/example/jspwar/JspWarApplication.java**

~~~java
package com.example.jspwar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class JspWarApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(JspWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(JspWarApplication.class, args);
    }
}
~~~

**main()** phục vụ executable WAR chạy bằng **java -jar**. **SpringBootServletInitializer.configure(...)** là integration point để một Servlet container bên ngoài khởi tạo Spring Boot từ WAR. Đối với ứng dụng chỉ chạy standalone không cần external deploy, phần initializer không phải lúc nào cũng bắt buộc; ở bài này khai báo nó để có đủ **hai chế độ chạy**.

### 6.4. Controller trả JSP view

**src/main/java/com/example/jspwar/PageController.java**

~~~java
package com.example.jspwar;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {
    @GetMapping("/ui/hello")
    public String hello(Model model) {
        model.addAttribute("greeting", "Chao tu JSP WAR!");
        return "hello";
    }
}
~~~

**return "hello"** là logical view name, không phải body string. **@Controller** không nên tự chuyển thành @RestController nếu muốn render JSP. Model được gửi tới view, nơi JSP EL/JSTL đọc dữ liệu.

### 6.5. API không phụ thuộc JSP

**src/main/java/com/example/jspwar/ApiController.java**

~~~java
package com.example.jspwar;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }
}
~~~

REST endpoint có thể hoạt động dù JSP engine bị lỗi. Chính vì vậy **API 200 không đủ chứng minh JSP đã được render thành công**.

### 6.6. View resolver

**src/main/resources/application.properties**

~~~properties
spring.application.name=jsp-war
server.port=8080
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
~~~

Spring MVC view resolver ghép:

~~~text
logical view: hello
prefix:       /WEB-INF/jsp/
suffix:       .jsp
ket qua:      /WEB-INF/jsp/hello.jsp
~~~

Đường dẫn view là Servlet webapp resource, không phải file path của JVM bên ngoài JAR. **Prefix** nên kết thúc bằng dấu **/**, **suffix** là **.jsp**. Không gắn **.jsp** trực tiếp vào string controller khi đã có suffix, tránh thành **hello.jsp.jsp**.

### 6.7. File JSP thực sự

**src/main/webapp/WEB-INF/jsp/hello.jsp**

~~~jsp
<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>JSP WAR</title>
</head>
<body>
    <h1><c:out value="${greeting}" /></h1>
</body>
</html>
~~~

Thẻ **c:out** của JSTL xuất nội dung model thành HTML text và escape ký tự đặc biệt theo mặc định. Tránh nhúng input không được kiểm soát vào HTML bằng scriptlet hoặc expression không escape. Không cần scriptlet Java **<% ... %>** cho ví dụ này.

### 6.8. Test logic controller, nhưng phải smoke test WAR thật

**src/test/java/com/example/jspwar/PageControllerTest.java**

~~~java
package com.example.jspwar;

import org.junit.jupiter.api.Test;
import org.springframework.ui.ExtendedModelMap;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PageControllerTest {
    @Test
    void returnsJspLogicalViewName() {
        ExtendedModelMap model = new ExtendedModelMap();
        String viewName = new PageController().hello(model);

        assertEquals("hello", viewName);
        assertEquals("Chao tu JSP WAR!",
                model.getAttribute("greeting"));
    }
}
~~~

Test này xác nhận controller chọn logical view name và set model đúng, nhưng **không load Servlet container, không chạy Jasper và không kiểm tra WAR packaging**. Đó là giới hạn có chủ đích: test cho JSP compatibility cần thêm HTTP smoke test trên **artifact đã đóng gói**.

### 6.9. Build và chạy executable WAR

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/jsp-war-0.0.1-SNAPSHOT.war
~~~

Windows (PowerShell hoặc CMD):

~~~text
mvnw.cmd clean package
java -jar target/jsp-war-0.0.1-SNAPSHOT.war
~~~

Nếu project không có Maven wrapper, sử dụng Maven tương thích theo lệnh **mvn clean package**. Tên WAR trong ví dụ khớp **artifactId=jsp-war**, **version=0.0.1-SNAPSHOT**; đổi lệnh theo artifact thực tế nếu project khác.

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/ui/hello
curl -i http://localhost:8080/api/status
~~~

**Kỳ vọng thứ nhất:** HTTP 200, Content-Type HTML và body có:

~~~html
<h1>Chao tu JSP WAR!</h1>
~~~

**Kỳ vọng thứ hai:** HTTP 200, Content-Type JSON và body có:

~~~json
{"status":"ok"}
~~~

Thứ tự key JSON trong ví dụ chỉ có một key nên body thường đúng như trên; HTTP header, charset và khoảng trắng trong toàn bộ HTML có thể khác tùy môi trường. **GET /WEB-INF/jsp/hello.jsp** không nên trả nội dung JSP trực tiếp cho client.

**Quan trọng:** build thành công chỉ chứng minh Java và packaging qua được quá trình build; **JSP có thể chỉ được biên dịch khi request lần đầu đến**. Phải thực sự gọi **/ui/hello** trên executable WAR và kiểm tra status/body/log của server.

### 6.10. Kiểm tra nội dung WAR

Dùng công cụ **jar** của JDK:

~~~bash
jar tf target/jsp-war-0.0.1-SNAPSHOT.war
~~~

Trong danh sách entry, tìm **WEB-INF/jsp/hello.jsp**, **WEB-INF/classes/** và các thư viện cần thiết. Khi Spring Boot repackage executable/deployable WAR với các dependency provided phù hợp, có thể thấy **WEB-INF/lib-provided/**. Nếu **WEB-INF/jsp/hello.jsp** không có trong WAR, view resolver không thể tạo ra file từ không khí.

Khi báo lỗi, lưu lại **artifact name, Java version, Spring Boot version, runtime server, log root cause, URL/status** để phân biệt lỗi build, lỗi đóng gói, lỗi server và lỗi view.

## 7. Deploy cùng WAR vào Tomcat bên ngoài

Với ứng dụng mẫu, **JspWarApplication extends SpringBootServletInitializer** cho phép Servlet container bên ngoài bootstrap Spring context. Quy trình khái niệm:

1. Build **jsp-war-0.0.1-SNAPSHOT.war**.
2. Xác nhận external Tomcat tương thích **Jakarta Servlet/JSP** của ứng dụng; ví dụ Tomcat **10.1** phù hợp thế hệ Spring Boot 3.3 hơn Tomcat 9.
3. Deploy WAR qua cơ chế quản lý của container. **Đừng đổi port embedded trong application.properties rồi coi đó là cấu hình port external Tomcat**: container ngoài quyết định connector/port.
4. Xác định context path thực tế của deployment (tên WAR hoặc cấu hình context). Nếu ứng dụng deploy dưới **/jsp-war**, URL sẽ có tiền tố này.
5. Gọi cả **/jsp-war/ui/hello** và **/jsp-war/api/status**, đối chiếu HTML/JSON.
6. Kiểm tra xung đột thư viện được đóng gói và các JSP/JSTL module của container; tránh duplicate Servlet/JSP engine trong **WEB-INF/lib**.

Nếu deploy WAR dưới tên **ROOT.war** vào context root phù hợp, URL bên ngoài có thể không có prefix application name. Đừng áp dụng máy móc cùng một URL cho executable WAR và external WAR. Cần kiểm chứng **port, context path, reverse proxy mapping và security rule** trên hệ thật.

**Khác biệt quyền sở hữu:** trong **java -jar .war**, Boot khởi động container nhúng; trong external WAR, container ngoài kiểm soát startup/shutdown và ServletContext. Đây là lý do cần đúng **provided** scope để không đem runtime Tomcat riêng của Boot vào classpath ứng dụng khi container ngoài đã có engine.

## 8. Gradle và quy tắc providedRuntime tương đương

Nếu project dùng Gradle, không bắt buộc chuyển sang Maven chỉ để dùng JSP. Cần dùng **war plugin** để tạo WAR và **providedRuntime** cho servlet container. Dưới đây là **đoạn dependency minh họa** cho Spring Boot **3.3.x** trong một project Gradle đã áp dụng Java, Spring Boot, dependency management và war plugin:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    providedRuntime 'org.apache.tomcat.embed:tomcat-embed-jasper'
    implementation 'jakarta.servlet.jsp.jstl:jakarta.servlet.jsp.jstl-api'
    implementation 'org.glassfish.web:jakarta.servlet.jsp.jstl'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Build và chạy:

~~~bash
./gradlew clean bootWar
java -jar build/libs/jsp-war-0.0.1-SNAPSHOT.war
~~~

Trên Windows dùng **gradlew.bat clean bootWar**. Khi **war plugin** được bật, Spring Boot Gradle plugin tạo task **bootWar**, với dependency được phân loại để runnable WAR và deployable WAR không trộn thư viện của external container.

**Đừng nhầm:**

- **bootJar** tạo executable JAR, không phù hợp để xác nhận JSP.
- **bootWar** tạo executable WAR, phù hợp cho JSP nếu server/JSP engine đúng.
- **war** thường tạo WAR thường; cách đóng gói có thể khác bootWar.
- **implementation** và **providedRuntime** không cùng ý nghĩa; dependency container cần nằm ở chỗ phù hợp cho cả embedded và external.
- Thêm plugin war **không tự sửa** vị trí JSP sai hoặc thiếu Jasper/JSTL.

Đoạn Gradle chọn version để minh họa nhất quán với Maven. Khi project có build convention riêng hoặc wrapper Gradle riêng, hãy dùng version và plugin đã được project quản lý thay vì chồng thêm cấu hình trùng lặp.

## 9. Những giới hạn JSP khác vẫn tồn tại dù dùng WAR

### 9.1. error.jsp không tự thay giao diện lỗi của Spring Boot

Trong Spring Boot, thêm một file **error.jsp** tùy ý không tự động thay thế **default error view**. Spring Boot có cơ chế **/error**, **BasicErrorController**, ErrorAttributes, view resolver và các đường dẫn custom error page theo status. Tài liệu JSP limitations nêu rõ phải **cấu hình custom error page phù hợp** nếu muốn thay cách hiển thị lỗi.

Ví dụ phổ biến và đơn giản hơn cho HTTP 404 là tạo **src/main/resources/public/error/404.html** theo cơ chế custom error pages của Spring Boot, hoặc dùng template/error view resolver được thiết kế riêng. Không coi **/WEB-INF/jsp/error.jsp** là một quy ước đủ để bắt mọi error.

Khi ứng dụng vừa trả JSP cho browser vừa trả JSON cho API, cần kiểm tra **Accept**, Content-Type và status; đừng để một fallback JSP trả HTML 200 cho lỗi API đáng lẽ 404/500. Custom error handler không được làm lộ stack trace, credential hoặc dữ liệu nhạy cảm.

### 9.2. JSP không nằm trong src/main/resources/templates

Nhiều template engine được Spring Boot auto-config tìm dưới **classpath:/templates/**. Với JSP, view resolver thường forward tới **Servlet resource** như **/WEB-INF/jsp/**. Hai cơ chế không tương đương. Di chuyển JSP sang **resources/templates** để dùng cùng đường dẫn Thymeleaf không bảo đảm hoạt động.

Đặt **src/main/webapp/WEB-INF/jsp** phù hợp WAR. Với executable JAR, **src/main/webapp** thường không được đóng gói như Servlet resource, nên đây không phải “cách lách” hỗ trợ JSP cho JAR.

### 9.3. JSP cần JSP engine ngay cả khi controller trả view đúng

Một controller trả **"hello"**, view resolver biết path và Spring context khởi động không chứng minh Jasper hiện diện. JSP có thể cần compilation lần đầu khi truy cập. Smoke test phải được chạy trong cùng **server + artifact + classpath** như deployment dự kiến, không chỉ chạy **MockMvc**.

### 9.4. JSTL Jakarta khác thư viện javax/JSTL cũ

Với Spring Boot 3.x/Jakarta Tags 3.0, các dependency và URI phải khớp. Ví dụ trong bài dùng:

~~~jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<c:out value="${greeting}" />
~~~

Hướng dẫn cũ của Spring Boot 1.x/2.x có thể dùng **javax.servlet** và taglib URI như **http://java.sun.com/jsp/jstl/core**. Đừng sao chép nguyên cấu hình cũ vào project Boot 3 rồi kết luận JSP không hỗ trợ. Hãy chọn JSTL API/implementation đúng dòng Jakarta và kiểm tra dependency tree.

**Bảo mật:** dùng **c:out** hoặc cơ chế escape HTML phù hợp cho dữ liệu không tin cậy. JSP scriptlet cũ nhúng Java trực tiếp trong trang gây khó kiểm thử, khó bảo trì và dễ mắc lỗi escaping; nên để nghiệp vụ trong controller/service và view chỉ trình bày dữ liệu.

### 9.5. Test bằng MockMvc có giới hạn

**MockMvc** kiểm tra Spring MVC handler, model, status, redirect hoặc logical view name mà không mở một JSP-capable container thực tế. Test **view().name("hello")** có thể PASS ngay cả khi WAR thiếu file JSP hoặc Jasper không hiện diện. Chỉ xem test đó là một lớp kiểm tra; muốn xác minh server compatibility phải **build WAR rồi request JSP qua HTTP thật**.

### 9.6. Servlet stack và reactive stack không dùng chung JSP view path

JSP thuộc mô hình Servlet server-side view. Spring WebFlux sử dụng reactive view rendering và các template engine phù hợp; không bật JSP bằng cách thêm **spring.mvc.view.prefix** vào một app thuần WebFlux. Việc dùng Tomcat làm HTTP server cho reactive stack không tự động biến WebFlux thành Spring MVC JSP application.

### 9.7. Native image và đóng gói đặc biệt

JSP có bước biên dịch/render động qua JSP engine và phụ thuộc servlet resource/class loading. Đừng mặc định rằng JSP WAR sẽ hoạt động nguyên trạng khi chuyển sang **GraalVM native image**, layered archive tùy biến hoặc runtime bỏ file system/resource. Nếu mục tiêu deployment là native image hoặc một executable JAR tối giản, nên đánh giá lại công nghệ render thay vì hứa hỗ trợ JSP chỉ vì build native thành công.

## 10. Quy trình xác minh theo từng tầng

Một kết luận **"JSP được hỗ trợ"** chỉ đáng tin khi đã kiểm tra đúng tầng:

| Tầng | Câu hỏi | Cách kiểm chứng |
| --- | --- | --- |
| **1. Build** | Build tool tạo đúng WAR chưa? | pom.xml packaging=war / Gradle war plugin; file .war xuất hiện. |
| **2. Artifact** | JSP có trong WEB-INF/jsp? | Liệt kê entry bằng jar tf; kiểm tra WEB-INF/jsp/hello.jsp. |
| **3. Dependency** | JSP compiler và JSTL đúng version? | Maven dependency:tree hoặc Gradle dependencies; đọc log ClassNotFoundException. |
| **4. Server** | Container thật là Tomcat/Jetty JSP-capable? | Startup log, dependency tree, cấu hình external container; loại trừ Undertow. |
| **5. MVC** | Controller chọn JSP view? | @Controller return view name; prefix/suffix đúng; test model/view. |
| **6. HTTP** | JSP thực sự render? | curl -i URL JSP qua controller; status 200, Content-Type text/html, HTML mong đợi. |
| **7. Compatibility** | Cùng WAR có chạy ở mục tiêu khác? | Smoke test độc lập trên embedded WAR và external container được hỗ trợ. |
| **8. Operations** | Error page, URL prefix, security, encoding đúng? | Test 404, API JSON, HTML escaping, context path và log. |

Không kết luận hỗ trợ chỉ từ **mvn test PASS**, **Spring started** hoặc **GET /api/status trả 200**. Ba tín hiệu đó đều có thể đúng trong khi Jasper không render được trang nào.

## 11. Chẩn đoán lỗi thực tế

### 11.1. Chạy trong IDE được, java -jar .jar lỗi JSP

**Triệu chứng:** IDE chạy view đúng, executable JAR trả 404/Whitelabel error hoặc JSP không tìm thấy. **Nguyên nhân ưu tiên:** JSP không được hỗ trợ với **executable JAR**, vị trí **src/main/webapp** không được đóng gói theo Servlet WAR. **Cách xử lý:** chuyển build sang **WAR**, chạy **java -jar file.war** trên Tomcat/Jetty hỗ trợ JSP; hoặc chuyển JSP sang template engine phù hợp JAR nếu muốn giữ artifact JAR.

Đừng tiếp tục thử thêm dependency Jasper vào JAR mà không đổi packaging: điều này không làm mất giới hạn đã được tài liệu Spring Boot nêu rõ.

### 11.2. WAR khởi động nhưng HTTP 500 khi mở JSP

**Nghi ngờ:** thiếu **tomcat-embed-jasper**, JSP compilation error, lỗi JSTL taglib, trộn Javax/Jakarta, thiếu class trong runtime, sai version container/JSP engine. **Kiểm tra:** xem exception gốc trong server log, dependency tree, các entry lib-provided/lib và đường dẫn JSP. **Sửa:** đồng bộ dependency BOM, thêm JSP engine đúng server, dùng Jakarta taglib, kiểm tra cú pháp JSP.

Lỗi xảy ra khi request đầu tiên đến cũng hợp lý vì JSP có thể được compile lúc sử dụng. Không suy ra ứng dụng startup thành công là JSP compilation đã chạy.

### 11.3. 404 trên /ui/hello

**Nghi ngờ:** chưa scan được @Controller, @GetMapping sai, servlet context path khác, WAR deploy dưới prefix, view path sai hoặc thiếu file JSP trong WAR. **Kiểm tra:** gọi /api/status với cùng base URL, xem log mapping, liệt kê WAR, kiểm tra request URL thật.

Phân biệt **404 do controller không match** với **lỗi tìm view/JSP resource**: một loại xảy ra trước khi chọn handler, một loại sau khi view resolver xử lý.

### 11.4. Browser hiển thị chữ hello thay cho trang

**Nghi ngờ:** dùng **@RestController**, **@ResponseBody** hoặc method trả text/plain. **Sửa:** dùng **@Controller** với logical view name, không trả trực tiếp đường dẫn file JSP dưới dạng body. Nếu body hiển thị nguyên source JSP, kiểm tra JSP engine/Servlet mapping và cách resource bị public; không cho browser tải source JSP trực tiếp.

### 11.5. Circular view path hoặc 500 khi resolve view

**Nghi ngờ:** view resolver không có prefix/suffix, view name trùng URL handler, forward quay lại chính handler hoặc view không tồn tại. **Sửa:** set **spring.mvc.view.prefix=/WEB-INF/jsp/** và **spring.mvc.view.suffix=.jsp**, dùng tên view **"hello"** thay vì URL **"/ui/hello"**, xác nhận JSP dưới WEB-INF.

Không thêm **@EnableWebMvc** một cách ngẫu nhiên để sửa view: nó có thể làm thay đổi nhiều MVC auto-configuration khác.

### 11.6. NoClassDefFoundError: javax.servlet.* hoặc jakarta.servlet.*

**Nghi ngờ:** WAR Boot 3.x chạy trong Tomcat 9/Servlet API cũ, hoặc đưa dependency javax từ project Boot 2.x vào runtime Jakarta. **Sửa:** dùng container tương thích Jakarta và dependency version thống nhất; loại thư viện cũ không phù hợp. Tránh “sửa” bằng cách thêm cả javax và jakarta cùng lúc.

### 11.7. Tomcat chạy được, Jetty hoặc Undertow không chạy

**Jetty:** kiểm tra đúng module JSP, version Jetty/Servlet Jakarta, class loader và WAR packaging; tài liệu chỉ nói **WAR should work**, không bảo đảm setup nào cũng tự động đầy đủ.

**Undertow:** không hỗ trợ JSP trong ngữ cảnh tài liệu Spring Boot. Chọn container JSP-capable hoặc thay công nghệ view; không giải quyết bằng đổi prefix/suffix.

### 11.8. Đặt error.jsp nhưng vẫn thấy error mặc định

**Nguyên nhân:** Spring Boot đã có pipeline **/error** và cơ chế error view; một JSP mang tên error.jsp không tự override. **Sửa:** cấu hình custom error page theo status (ví dụ public/error/404.html), template/error view resolver hoặc ErrorController phù hợp, đồng thời giữ status HTTP đúng.

### 11.9. Cùng WAR chạy standalone nhưng deploy ngoài lỗi

**Nghi ngờ:** external container không tương thích Jakarta/Servlet, trùng dependency của container trong WEB-INF/lib, thiếu JSP engine ở container ngoài, context path thay đổi, JNDI/service expectation khác. **Kiểm tra:** scope provided, jar tf, log container ngoài, Java version và WAR classpath. Không suy luận rằng **java -jar .war chạy được** chứng minh mọi external server đều tương thích.

## 12. Chọn JSP hay công nghệ view khác?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Bảo trì ứng dụng Spring MVC lớn vốn có JSP/JSTL | **Giữ JSP, dùng WAR + Tomcat/Jetty đã kiểm thử** | Giảm chi phí chuyển đổi, bảo toàn view hiện có trong phạm vi support. |
| Dự án mới, server-side HTML với executable JAR | **Thymeleaf, FreeMarker hoặc Mustache** | Template classpath:/templates, không phụ thuộc JSP WAR packaging. |
| REST API + frontend SPA/SSR độc lập | **API JSON và frontend riêng** | Giảm dependency của backend vào JSP engine và Servlet view path. |
| Muốn đổi giữa Tomcat, Jetty và Undertow dễ dàng | **Tránh JSP** | JSP không được hỗ trợ đồng đều trên container. |
| Bắt buộc Undertow | **Không thiết kế JSP như view engine** | Undertow không hỗ trợ JSP theo tài liệu Spring Boot. |
| Bắt buộc executable JAR | **Chọn template engine khác** | Spring Boot không hỗ trợ JSP trong executable JAR. |
| WAR triển khai vào Tomcat ngoài hiện có | **JSP có thể phù hợp**, xác minh Jakarta và scope | Servlet/JSP engine có sẵn ở container; vẫn phải smoke test. |

Spring Boot khuyến nghị **tránh JSP nếu có lựa chọn phù hợp**, vì có giới hạn với embedded Servlet container. Điều này không có nghĩa mọi ứng dụng JSP legacy phải viết lại ngay; quyết định nên dựa vào yêu cầu packaging/server, khả năng kiểm thử, chi phí migration và đường nâng cấp lâu dài.

## 13. Checklist quyết định và nghiệm thu

- [ ] Đã xác nhận ứng dụng dùng **Spring MVC Servlet**, không nhầm với WebFlux.
- [ ] Đã xác nhận container thực tế: Tomcat, Jetty, Undertow hoặc external Servlet container khác.
- [ ] Nếu phải dùng JSP, đã chọn **WAR packaging** phù hợp; không xem executable JAR là lựa chọn được hỗ trợ.
- [ ] Nếu dùng Undertow, đã bỏ yêu cầu JSP hoặc chọn server khác.
- [ ] JSP nằm ở **src/main/webapp/WEB-INF/jsp/** và thật sự có trong WAR sau build.
- [ ] **@Controller** trả logical view name; **@RestController** dành cho API body.
- [ ] **spring.mvc.view.prefix/suffix** khớp đường dẫn Servlet resource, không bị ghép lặp .jsp.
- [ ] Có JSP engine tương thích; với Tomcat nhúng đã kiểm tra **tomcat-embed-jasper**.
- [ ] Dependency Servlet/JSP/JSTL thuộc **Jakarta** tương thích Spring Boot 3.x.
- [ ] Container runtime dùng **provided / providedRuntime** khi build WAR phục vụ cả standalone và external deploy.
- [ ] Có **SpringBootServletInitializer** nếu cần deploy WAR vào external Servlet container.
- [ ] Đã chạy **java -jar app.war** và kiểm tra trang JSP thực sự render HTML qua HTTP.
- [ ] Đã smoke test WAR trên external container đích, tính cả context path và security.
- [ ] Có test API JSON độc lập; API 200 không được dùng thay cho JSP smoke test.
- [ ] Custom error page được cấu hình theo cơ chế Spring Boot, không chỉ đặt error.jsp.
- [ ] Không công khai source JSP ngoài WEB-INF; dữ liệu render được escape HTML.
- [ ] Đã có phương án thay JSP nếu chuyển sang executable JAR, Undertow hoặc native deployment.

### Câu hỏi tự kiểm tra

**1. Có thể chạy Spring MVC REST API bằng executable JAR + Tomcat không?** Có. Giới hạn được nói đến ở đây là **JSP**, không phải toàn bộ Spring MVC hoặc embedded Tomcat.

**2. Chỉ cần thêm tomcat-embed-jasper vào executable JAR là đủ?** Không. Tài liệu Spring Boot không hỗ trợ JSP khi packaging là executable JAR. Chuyển sang WAR hoặc thay template engine.

**3. Executable WAR có bắt buộc cài Tomcat bên ngoài?** Không. WAR được Spring Boot plugin repackages đúng có thể chạy **java -jar app.war** bằng embedded container, đồng thời có thể deploy vào container ngoài tương thích.

**4. Vì sao dependency Tomcat/Jasper dùng provided khi deploy ngoài?** Vì container ngoài đã có runtime Servlet/JSP; phân loại provided giúp tránh trộn class library của container với classpath ứng dụng. Với Boot executable WAR, các dependency đó có thể nằm trong lib-provided để sử dụng khi chạy standalone.

**5. Jetty và Undertow giống nhau về JSP?** Không. Spring Boot nêu Jetty + WAR **should work** khi setup tương thích, còn Undertow **không hỗ trợ JSP**.

**6. Vì sao @Controller return "hello" là khác @RestController return "hello"?** @Controller chọn view qua view resolver, còn @RestController trả string vào body HTTP.

**7. Nếu MockMvc test viewName PASS, có cần test WAR nữa không?** Có. MockMvc không xác nhận Jasper, servlet resource layout và deployment ngoài. Chỉ HTTP smoke test trên WAR mới kiểm tra được toàn bộ chuỗi.

**8. Tại sao error.jsp không tự hiện khi API lỗi?** Spring Boot có cơ chế /error, error view và content negotiation riêng. Phải dùng custom error page hoặc error handler có chủ đích.

## 14. Tài liệu chính thức

1. [Spring Boot 3.3 — Servlet Web Applications: JSP Limitations](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): nguồn trực tiếp cho ma trận JSP, executable JAR/WAR, Undertow và error.jsp.
2. [Spring Boot 3.3 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html): hướng dẫn WAR, SpringBootServletInitializer, Maven provided, Gradle providedRuntime và deploy vào container ngoài.
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): spring.mvc.view.prefix và spring.mvc.view.suffix.
4. [Spring Framework — JSP and JSTL](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-jsp.html): InternalResourceViewResolver và khuyến nghị đặt JSP dưới WEB-INF.
5. [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java, Servlet container và baseline Spring Framework tương thích.

**Điểm kết nối quan trọng:** chọn JSP là chọn đồng thời **công nghệ view, JSP-capable Servlet server, WAR artifact, vị trí JSP trong WAR và đúng Jakarta dependencies**. Quy trình build và HTTP smoke test phải bám **đúng container + đúng kiểu đóng gói dùng khi triển khai**; một ứng dụng chạy được trong IDE hoặc REST API trả 200 chưa đủ để kết luận JSP hoạt động.