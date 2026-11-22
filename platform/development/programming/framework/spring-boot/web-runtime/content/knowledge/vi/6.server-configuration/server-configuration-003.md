# server.servlet.context-path, spring.mvc.servlet.path và spring.webflux.base-path trong Spring Boot

> **Phạm vi:** Spring Boot **3.5.x**, Java **17+**. Bài này phân biệt ba thuộc tính cấu hình URL của ứng dụng Spring Boot, cách chúng tác động đến **Spring MVC (Servlet)** và **Spring WebFlux (reactive)**, cách tính URL cuối cùng, ví dụ Maven có thể chạy, kiểm thử tích hợp và lỗi thường gặp. Các ví dụ đặt phiên bản Spring Boot ở mức **3.5.0** để cấu trúc dependency/import nhất quán; khi nâng cấp hãy đọc tài liệu của phiên bản đang chạy.

## 1. Ba thuộc tính cùng nói về “đường dẫn”, nhưng tác động ở ba tầng khác nhau

Trong HTTP, URL có thể được hình dung là:

~~~text
scheme://host:port / context-path / servlet-path / controller-mapping ? query

Ví dụ MVC:
http://localhost:8080 /portal       /api          /hello

Ví dụ WebFlux:
http://localhost:8081 /gateway                    /hello
~~~

**Chú ý:** Đây là mô hình tư duy để nối các phần của đường dẫn, không phải cú pháp cấu hình hay quy tắc phân rã URL áp dụng cho mọi server. Trong trường hợp Servlet API, `contextPath` và `servletPath` còn là các khái niệm cụ thể trong `HttpServletRequest`.

| Thuộc tính | Áp dụng cho | Cấp tác động | Khi endpoint là `@GetMapping("/hello")` |
|---|---|---|---|
| `server.servlet.context-path=/portal` | Ứng dụng **Servlet** như Spring MVC | Context path của web application trong servlet container | `/portal/hello` nếu DispatcherServlet ở mặc định |
| `spring.mvc.servlet.path=/api` | **Spring MVC** | Mapping/prefix của `DispatcherServlet` | `/api/hello` nếu context path mặc định |
| `spring.webflux.base-path=/gateway` | **Spring WebFlux** | Base path cho các WebFlux web handler | `/gateway/hello` trong reactive app |
| `server.port=8080` | Cả hai loại khi dùng embedded server tương ứng | Cổng TCP | Chỉ đổi `host:port`, không tự thêm prefix |

Những thuộc tính này **không thể thay thế tùy ý cho nhau**. Đổi từ Servlet MVC sang WebFlux là thay đổi web stack và dependency, không chỉ đổi tên property.

Các giá trị mặc định thường là context path rỗng/ở root, mapping DispatcherServlet `/`, base path WebFlux không có prefix. Khi không chỉnh đường dẫn, controller `/hello` thường có URL `http://localhost:8080/hello`.

## 2. `server.servlet.context-path`: đường dẫn của cả ứng dụng Servlet

Đây là **context path của web application** theo Servlet API, được embedded Tomcat/Jetty/Undertow sử dụng khi chạy Spring MVC. Trong `application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/portal
~~~

Controller đơn giản:

~~~java
@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
~~~

Nếu không cấu hình `spring.mvc.servlet.path`, URL kiểm tra là:

~~~http
GET http://localhost:8080/portal/hello
~~~

Không phải `http://localhost:8080/hello`.

**Phạm vi tác động:** context path đặt ứng dụng Servlet dưới tiền tố `/portal`. Nó có thể ảnh hưởng đến các servlet, filters, controller MVC, servlet registration, tài nguyên tĩnh, các endpoint được triển khai trong cùng context và URL của cookie session. Đây là lý do nên ưu tiên thuộc tính này khi yêu cầu là “toàn bộ ứng dụng Servlet chạy dưới `/portal`”.

Ví dụ Servlet API: ở request `/portal/hello`, `request.getContextPath()` thường bằng `/portal`. Controller vẫn khai báo `@GetMapping("/hello")`: không cần thêm `/portal` vào annotation.

**Không nhầm với reverse proxy:** nếu ứng dụng chạy trong container ở context path `/portal` nhưng một API gateway công bố `https://example.com/app/portal/hello`, phần `/app` có thể do proxy tạo hoặc rewrite. `server.servlet.context-path` chỉ mô tả context do servlet container phục vụ bên trong ứng dụng.

## 3. `spring.mvc.servlet.path`: prefix của DispatcherServlet trong Spring MVC

`DispatcherServlet` là servlet trung tâm của Spring MVC: tiếp nhận request dành cho MVC rồi phối hợp `HandlerMapping`, controller, converter và view resolver. Mặc định nó xử lý phần gốc của Servlet context, thường được map tại `/`.

Trong một ứng dụng MVC:

~~~properties
spring.mvc.servlet.path=/api
~~~

Controller `@GetMapping("/hello")` sẽ được truy cập qua `/api/hello` (khi context path mặc định). Thuộc tính này **thay đổi mapping của DispatcherServlet**, không thay Servlet context path của toàn bộ ứng dụng.

Giả sử ứng dụng đăng ký thêm một servlet độc lập, không đi qua Spring MVC. Servlet đó có thể có mapping riêng, chịu `server.servlet.context-path` nhưng **không tự động** chịu prefix của MVC DispatcherServlet. Đây là khác biệt thực tế giữa hai thuộc tính.

### 3.1. Lưu ý bắt buộc trong Spring Boot 3.5: PathPatternParser

Trong Spring Boot 3.5.x, Spring MVC mặc định dùng chiến lược `PathPatternParser` để match URL với controller. Theo tài liệu chính thức, chiến lược này **không tương thích với việc đặt prefix qua `spring.mvc.servlet.path`**.

Vì vậy, khi dùng prefix của DispatcherServlet trong Spring Boot 3.5.x, cần cấu hình chiến lược khác:

~~~properties
spring.mvc.servlet.path=/api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Khi chỉ đặt `server.servlet.context-path` mà để DispatcherServlet mapping mặc định, không cần đổi sang `ant-path-matcher` vì riêng context path không tạo prefix mapping cho servlet.

**Hệ quả thiết kế:** đổi matching strategy có thể ảnh hưởng đến cách diễn giải route pattern, dấu gạch chéo, placeholder và mẫu wildcard. Sau khi đổi, hãy chạy lại test cho những controller mapping có pattern phức tạp. Không sao chép cấu hình trên sang phiên bản Boot khác mà chưa xem tài liệu của phiên bản đó.

Tài liệu Boot 3.5 nêu rõ bất tương thích này và ví dụ `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` tại phần Servlet Web Applications.

## 4. Khi kết hợp hai prefix của Spring MVC

Ví dụ:

~~~properties
server.port=8080
server.servlet.context-path=/portal
spring.mvc.servlet.path=/api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Với:

~~~java
@RestController
@RequestMapping("/v1")
class GreetingController {
    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
~~~

Đường dẫn được ghép như sau:

~~~text
/portal      + /api              + /v1       + /hello
(context)      (DispatcherServlet) (class)     (method)

=> /portal/api/v1/hello
~~~

URL để gọi là `http://localhost:8080/portal/api/v1/hello`.

Đừng sửa controller thành `@RequestMapping("/portal/api/v1")`: khi đã có hai prefix từ cấu hình, làm vậy sẽ khiến đường dẫn bị lặp prefix (và dễ gây 404). Annotation của controller mô tả phần route **bên trong Spring MVC**, không mô tả context path hay mapping của chính DispatcherServlet.

Bảng ví dụ với cùng method `@GetMapping("/hello")`, **không có `@RequestMapping` ở class**:

| `server.servlet.context-path` | `spring.mvc.servlet.path` | Đường dẫn ngoài cùng |
|---|---|---|
| Không đặt | Không đặt | `/hello` |
| `/portal` | Không đặt | `/portal/hello` |
| Không đặt | `/api` | `/api/hello` |
| `/portal` | `/api` | `/portal/api/hello` |
| `/store` | `/rest` | `/store/rest/hello` |

Ở những hàng có `spring.mvc.servlet.path` khác mặc định, ví dụ trong bài dùng Spring Boot 3.5.x đều giả định đã cấu hình `ant-path-matcher`.

## 5. Ví dụ Maven Spring MVC hoàn chỉnh có thể chạy

Dựng project với cấu trúc:

~~~text
mvc-path-demo/
  pom.xml
  src/
    main/
      java/
        com/example/mvcpaths/
          MvcPathsApplication.java
          HelloController.java
      resources/
        application.properties
    test/
      java/
        com/example/mvcpaths/
          HelloControllerIntegrationTest.java
~~~

### 5.1. Maven build

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-path-demo</artifactId>
    <version>1.0.0</version>
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

Project dùng `spring-boot-starter-web`, tức **Spring MVC trên Servlet stack**. Việc đặt `spring.webflux.base-path` trong project này không làm đổi đường dẫn controller MVC.

### 5.2. Controller và entry point

Tạo `src/main/java/com/example/mvcpaths/MvcPathsApplication.java`:

~~~java
package com.example.mvcpaths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcPathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcPathsApplication.class, args);
    }
}
~~~

Tạo `src/main/java/com/example/mvcpaths/HelloController.java`:

~~~java
package com.example.mvcpaths;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1")
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello mvc";
    }
}
~~~

Tạo `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Toàn bộ Servlet application chạy dưới /portal:
server.servlet.context-path=/portal

# DispatcherServlet của Spring MVC chạy dưới /api:
spring.mvc.servlet.path=/api

# Spring Boot 3.5: prefix DispatcherServlet không tương thích
# với PathPatternParser mặc định:
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Hoặc build JAR:

~~~bash
mvn clean package
java -jar target/mvc-path-demo-1.0.0.jar
~~~

Request đúng:

~~~bash
curl -i http://localhost:8080/portal/api/v1/hello
~~~

Body phản hồi đúng của controller:

~~~text
hello mvc
~~~

Thử gọi thiếu một prefix:

~~~bash
curl -i http://localhost:8080/portal/v1/hello
curl -i http://localhost:8080/api/v1/hello
~~~

Trong app mẫu (không có controller khác cho hai địa chỉ này), request sẽ không match controller và thường trả HTTP **404 Not Found**.

Nếu `8080` đã bị chiếm, có thể chạy với port khác bằng tham số chương trình:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=9090
~~~

Cổng đổi sang 9090, **đường dẫn `/portal/api/v1/hello` không đổi**.

### 5.3. Kiểm thử tích hợp trên cổng động

Tạo `src/test/java/com/example/mvcpaths/HelloControllerIntegrationTest.java`:

~~~java
package com.example.mvcpaths;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HelloControllerIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void receivesRequestWithContextAndServletPrefix() throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/portal/api/v1/hello");
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());
        assertEquals("hello mvc", response.body());
    }

    @Test
    void doesNotMatchWhenServletPrefixIsMissing() throws Exception {
        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/portal/v1/hello");
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(404, response.statusCode());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Trong bài test, `RANDOM_PORT` mở embedded server thật trên cổng OS chọn; `@LocalServerPort` nhận cổng thực tế. `server.servlet.context-path` và `spring.mvc.servlet.path` vẫn được áp dụng, vì `RANDOM_PORT` thay đổi cổng chứ không bỏ prefix.

**Chú ý về `MockMvc`:** khi dùng mock request thay vì web server thật, bạn có thể phải khai báo `contextPath` và `servletPath` trong request builder để tái hiện chính xác URL servlet. Nếu mục tiêu là kiểm tra đường dẫn cuối cùng mà client gọi, một integration test HTTP thật như trên sẽ rõ ràng hơn.

## 6. `spring.webflux.base-path`: base path cho ứng dụng WebFlux

Spring WebFlux là stack lập trình reactive của Spring. Khi ứng dụng dùng WebFlux chạy trên Reactor Netty (không dùng Servlet context của Spring MVC), thuộc tính:

~~~properties
spring.webflux.base-path=/gateway
~~~

đặt base path cho **các WebFlux web handler**. Ví dụ một reactive controller `@GetMapping("/hello")` được truy cập tại `/gateway/hello`.

Cấu hình này không phải là một alias của `server.servlet.context-path` và không phải là mapping của `DispatcherServlet`: ứng dụng WebFlux thuần không xử lý HTTP qua MVC DispatcherServlet.

### 6.1. Maven project WebFlux độc lập

Tạo một project **khác** với cấu trúc:

~~~text
webflux-path-demo/
  pom.xml
  src/main/java/com/example/webfluxpaths/ReactivePathsApplication.java
  src/main/resources/application.properties
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-path-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/java/com/example/webfluxpaths/ReactivePathsApplication.java`:

~~~java
package com.example.webfluxpaths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactivePathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactivePathsApplication.class, args);
    }
}

@RestController
class ReactiveHelloController {
    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("hello reactive");
    }
}
~~~

Để hai class cùng nằm trong file này, chỉ `ReactivePathsApplication` là `public`; `ReactiveHelloController` là top-level class package-private, cú pháp **hợp lệ trong Java 17**. Tên file khớp class public.

`src/main/resources/application.properties`:

~~~properties
server.port=8081
spring.webflux.base-path=/gateway
~~~

Chạy:

~~~bash
mvn spring-boot:run
~~~

Gọi:

~~~bash
curl -i http://localhost:8081/gateway/hello
~~~

Body phản hồi:

~~~text
hello reactive
~~~

Nếu không có handler khác, `http://localhost:8081/hello` thường trả **404** vì thiếu `/gateway`. Khi dùng router function (`RouterFunction`) của WebFlux thay cho annotated controller, base path của WebFlux vẫn áp dụng cho các web handler được Spring Boot cấu hình.

Trong project WebFlux độc lập này, **không cần** `server.servlet.context-path` hoặc `spring.mvc.servlet.path`: chúng thuộc về Servlet/MVC và không phải cách cấu hình URL cho Reactor Netty WebFlux.

### 6.2. Khi đồng thời có hai web starter

Nếu project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường **ưu tiên loại ứng dụng Servlet MVC** khi tự xác định web application type. Một dependency WebFlux không tự làm controller chuyển sang reactive stack.

Vì vậy, nếu cấu hình `spring.webflux.base-path=/gateway` mà URL MVC không thay đổi, cần kiểm tra dependency và loại web application thực sự đang chạy. Đừng cố trộn ba property để ép URL hoạt động. Hãy xác định ứng dụng đang ở **MVC** hay **WebFlux** trước, rồi chọn property đúng với stack.

## 7. YAML tương đương và thay đổi cấu hình theo môi trường

### 7.1. Spring MVC (Servlet)

`application.yml`:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /portal

spring:
  mvc:
    servlet:
      path: /api
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

Các giá trị này tương đương ví dụ MVC trong `application.properties`. Không đặt **cùng một property với hai giá trị đối nghịch** ở nhiều nguồn cấu hình rồi suy ra thứ tự ghi đè theo cảm tính: thứ tự ưu tiên còn phụ thuộc command-line args, environment variables, profile và nguồn config.

### 7.2. WebFlux

`application.yml`:

~~~yaml
server:
  port: 8081

spring:
  webflux:
    base-path: /gateway
~~~

Nếu chỉ muốn public API xuất hiện dưới một prefix, lựa chọn cấu hình có thể nằm ở **ứng dụng** hoặc **gateway/ingress**. Khi đã có reverse proxy rewrite, phải xác định proxy có gửi prefix vào backend hay đã loại bỏ nó; cấu hình lặp ở cả proxy và app có thể dẫn đến **404** hoặc URL bị lặp.

### 7.3. Một số biến môi trường tương ứng

Spring Boot hỗ trợ relaxed binding cho property keys; những tên biến môi trường thường dùng trong container:

~~~text
SERVER_SERVLET_CONTEXT_PATH=/portal
SPRING_MVC_SERVLET_PATH=/api
SPRING_WEBFLUX_BASE_PATH=/gateway
~~~

Hãy đặt **chỉ các biến có ý nghĩa cho web stack hiện tại**. Nếu dùng `spring.mvc.servlet.path` với Spring Boot 3.5.x, đừng quên matching strategy phù hợp, ví dụ biến `SPRING_MVC_PATHMATCH_MATCHINGSTRATEGY=ant-path-matcher` hoặc đưa cấu hình vào file.

## 8. Giải thích theo tầng xử lý request

### 8.1. Servlet MVC

Request đến ứng dụng MVC theo chuỗi đơn giản hóa:

~~~text
HTTP client
    |
    v
embedded Servlet container (Tomcat/Jetty/Undertow)
    |
    +-- nhận Servlet context: /portal
    |
    +-- định tuyến servlet mapping: /api/*
            |
            v
        Spring MVC DispatcherServlet
            |
            +-- tìm controller theo /v1/hello
                    |
                    v
              @RequestMapping("/v1") + @GetMapping("/hello")
~~~

Hai cấp cấu hình nằm ngoài mapping của controller. Khi xem `HttpServletRequest`, ba thành phần `getContextPath()`, `getServletPath()` và `getPathInfo()` giúp nhận diện request đã được container phân chia thế nào. Các giá trị cụ thể của `servletPath` và `pathInfo` phụ thuộc kiểu servlet mapping, nên đừng luôn giả định chúng là các đoạn giống một phép `split("/")`.

### 8.2. WebFlux trên Reactor Netty

~~~text
HTTP client
    |
    v
Reactive server (ví dụ Reactor Netty)
    |
    +-- WebFlux base-path: /gateway
            |
            v
        WebFlux HandlerMapping
            |
            +-- route /hello
                    |
                    v
              @GetMapping("/hello") hoặc RouterFunction
~~~

Ở ứng dụng WebFlux này không có Servlet context path theo Servlet API, nên không cộng thêm `server.servlet.context-path` vào `spring.webflux.base-path`.

## 9. Spring Security, Actuator, static files và OpenAPI

Ba thuộc tính trên không chỉ liên quan đến controller. Đổi prefix có thể ảnh hưởng cấu hình và đường dẫn của các hệ thống phụ.

### Spring Security

Với Spring MVC, security filter chain là một phần của Servlet application, và request matcher có thể xem xét servlet path theo cách phụ thuộc loại matcher và phiên bản Spring Security. Nếu đổi `spring.mvc.servlet.path`, hãy kiểm tra **tất cả rule bảo vệ API**; đừng giả định rằng một pattern dùng trước khi đổi prefix vẫn match giống hệt sau đó.

Các test quan trọng: endpoint công khai phải truy cập được, endpoint cần đăng nhập phải trả 401/redirect thích hợp, endpoint đòi quyền phải trả 403 khi bị từ chối, và URL không hợp lệ không được vô tình đi qua đường xử lý bỏ qua xác thực.

Với WebFlux, security dựa trên reactive `SecurityWebFilterChain`, khác với servlet `SecurityFilterChain`. Đừng sao chép nguyên matcher giữa hai stack.

### Spring Boot Actuator

Khi có dependency Actuator và management endpoint dùng **cùng cổng** với ứng dụng, mặc định base path management thường là `/actuator`. Theo tài liệu Spring Boot, `management.endpoints.web.base-path` được hiểu **tương đối với `server.servlet.context-path`** trong Servlet MVC, hoặc **`spring.webflux.base-path`** trong WebFlux. Do đó, ví dụ:

~~~properties
server.servlet.context-path=/portal
management.endpoints.web.base-path=/actuator
~~~

gợi ý URL management cùng context như `/portal/actuator/health`, phụ thuộc endpoint có được expose và cấu hình bảo mật. Đừng tự cộng `spring.mvc.servlet.path=/api` vào URL Actuator theo suy đoán. Khi management server dùng cổng riêng (`management.server.port`), base path được xác định theo cấu hình management server riêng.

**Quan trọng:** ví dụ Maven phía trên không thêm Actuator, nên `/actuator/health` sẽ không có sẵn; đoạn này chỉ áp dụng khi thực sự tích hợp starter Actuator.

### Static resources, welcome page, lỗi 404

Spring MVC có resource handler và mapping tĩnh; khi thay context path hoặc DispatcherServlet mapping, URL JS/CSS, favicon và welcome page cũng có thể thay đổi. Kiểm tra đường dẫn trong HTML/template, URL tương đối/tuyệt đối và cache proxy. Với WebFlux, cấu hình `spring.webflux.static-path-pattern` khác với `spring.webflux.base-path`: property thứ nhất thay route cho static resources, property thứ hai đặt prefix cấp ứng dụng reactive.

Lỗi 404 không luôn do controller: có thể do servlet mapping, static resource handler hoặc gateway rewrite. Hãy xem URL **thực mà browser gửi**, không chỉ đường dẫn do frontend tự dựng.

### OpenAPI/Swagger và callback/redirect URL

Nếu dùng springdoc hoặc hệ thống OpenAPI khác, hãy kiểm tra nơi tài liệu API, Swagger UI và các URL server trong schema được phục vụ sau khi đổi prefix. Tương tự, OAuth callback, webhook và redirect URL có thể phải cập nhật ở hệ thống bên ngoài. Không giả định mọi integration tự động đọc lại prefix.

## 10. Reverse proxy, load balancer và X-Forwarded-Prefix

Một reverse proxy có thể nhận:

~~~text
https://example.com/public/v1/hello
~~~

và forward đến backend:

~~~text
http://127.0.0.1:8080/portal/api/v1/hello
~~~

URL frontend nhìn thấy và URL backend nhận có thể **khác nhau**, tùy proxy giữ, thêm hoặc bỏ prefix. Vì vậy:

1. Chụp/log request path tại cả proxy và ứng dụng khi debug.
2. Kiểm tra cấu hình rewrite, path prefix, context path, servlet mapping và controller mapping.
3. Xem xét các header `Forwarded`, `X-Forwarded-*` và cách Spring Boot xử lý chúng khi ứng dụng đứng sau trusted proxy.
4. Tránh đặt đồng thời prefix ở proxy và app nếu proxy đã forward đúng đường dẫn cuối.
5. Kiểm tra link/redirect được tạo từ request, đồng thời xác định scheme và host public thực tế.

`server.forward-headers-strategy` có thể giúp ứng dụng xử lý forwarded headers trong môi trường phù hợp, nhưng **không tự sửa mọi lỗi rewrite prefix**. Chỉ tin forwarded headers từ proxy đáng tin cậy; trong môi trường cho phép request trực tiếp từ client, việc tin các header client tự gửi có thể dẫn đến URL không đúng.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Gọi `/hello` bị 404 | Đã đặt context path, servlet path hoặc base path | Tính lại URL theo stack, gọi đủ các prefix |
| Chỉ đặt `spring.mvc.servlet.path` rồi mapping lỗi | Boot 3.5 mặc định `PathPatternParser` không tương thích prefix DispatcherServlet | Dùng `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` và kiểm thử lại route |
| Đặt `spring.webflux.base-path` nhưng MVC URL không đổi | Ứng dụng vẫn là Spring MVC | Kiểm tra starter và `WebApplicationType` |
| Đặt `server.servlet.context-path` nhưng reactive Netty URL không đổi | Property thuộc Servlet stack | Dùng `spring.webflux.base-path` cho WebFlux |
| URL thành `/portal/api/portal/api/hello` | Đã thêm prefix vào cả property và controller/gateway | Chỉ giữ prefix ở đúng tầng |
| Test MockMvc pass nhưng HTTP thật 404 | Test mock không mô phỏng đúng Servlet context/mapping | Bổ sung `@SpringBootTest(RANDOM_PORT)` với request thật |
| Actuator path khác URL dự đoán | Management base path và management port có scope riêng | Kiểm tra `management.endpoints.web.base-path`, `management.server.port` và tài liệu |
| Cookie/redirect sai đường dẫn | Context path đổi, proxy giữ prefix khác | Kiểm tra Set-Cookie Path, Location, forward headers |
| Rule Security không match như trước | Servlet prefix/stack ảnh hưởng request matchers | Kiểm thử rule 401/403 trên URL thực tế |
| Cùng port nhưng nội bộ/ngoài mạng dùng URL khác | Proxy/Ingress rewrite | So sánh request path tại từng hop |

Quy trình chẩn đoán 404 theo thứ tự:

1. Xác nhận ứng dụng chạy **Servlet MVC hay WebFlux** qua dependency và startup log.
2. Đọc **các property hiệu lực** của profile/môi trường hiện tại, đặc biệt context/servlet/base path.
3. Xem controller mapping `@RequestMapping` ở cấp class và `@GetMapping`/`@PostMapping` ở method.
4. Tạo URL dự kiến từ stack đang dùng: Servlet MVC có thể có **context + servlet + controller**; WebFlux có **base + controller**.
5. Gọi URL bằng curl trực tiếp vào backend, bỏ qua proxy để cô lập lỗi (khi môi trường cho phép).
6. Nếu direct backend đúng nhưng public URL sai, kiểm tra rewrite và forwarded headers tại proxy.
7. Kiểm thử cả API, static resources, security/Actuator và redirect để phát hiện lệch prefix.

## 12. Quy tắc chọn property

**Chọn `server.servlet.context-path` khi:** ứng dụng chạy Servlet MVC và bạn muốn di chuyển *toàn bộ Servlet web application* sang một context, ví dụ `/portal`; giá trị này rõ ràng hơn nếu yêu cầu chỉ đơn giản là “đặt app dưới một prefix”.

**Chọn `spring.mvc.servlet.path` khi:** ứng dụng đang dùng Spring MVC và bạn có yêu cầu cụ thể muốn map **riêng DispatcherServlet** dưới `/api`, tách khỏi mapping của các servlet khác. Với Spring Boot **3.5.x**, phải giải quyết bất tương thích `PathPatternParser` bằng matching strategy thích hợp và kiểm thử.

**Chọn `spring.webflux.base-path` khi:** ứng dụng đang thực sự chạy stack **WebFlux reactive**, ví dụ Reactor Netty, và bạn muốn đặt tiền tố cấp WebFlux handler; không gắn context/servlet path của MVC vào URL reactive.

**Không chọn cả ba cùng lúc** để cố làm một API có nhiều tiền tố: xác định runtime stack và trách nhiệm của từng tầng trước. Nếu có proxy, coi public URL là hợp đồng bên ngoài; cấu hình path nội bộ phải nhất quán với hợp đồng ấy.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — mô tả các property `server.servlet.context-path`, `spring.mvc.servlet.path`, `spring.webflux.base-path`.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html) — lưu ý `PathPatternParser` không tương thích khi DispatcherServlet dùng path prefix, cùng cách chọn `ant-path-matcher`.
- [Spring Boot — Spring MVC Configuration](https://docs.spring.io/spring-boot/how-to/spring-mvc.html) — đặt đường dẫn cho `DispatcherServlet`.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html) — kiến trúc WebFlux.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html) — đường dẫn Actuator tương đối với context/base path hoặc management server.
- [Spring Framework — Path Matching for Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html) — servlet mapping, `requestURI`, `servletPath` và `pathInfo`.

**Kết luận thực hành:** Với MVC, đường dẫn đến controller được xác định từ Servlet context path, DispatcherServlet mapping và controller mapping; với WebFlux, dùng WebFlux base path cộng route. Đổi đúng property cho đúng stack, đồng thời kiểm thử URL thực bằng HTTP, sẽ tránh phần lớn lỗi 404 do tiền tố đường dẫn.
