# Quan hệ giữa Jersey, tài nguyên tĩnh và DispatcherServlet trong Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → **Mở rộng nền tảng web**. Bài học giải thích cách **Jersey (JAX-RS/Jakarta REST)**, **Spring MVC DispatcherServlet** và **Spring MVC static resource handler** có thể cùng hiện diện trong một ứng dụng Spring Boot. Trọng tâm không phải “bật cả hai dependency là xong”, mà là **Servlet URL mapping ở container**, sự khác nhau giữa **Jersey ServletContainer (servlet)** và **Jersey filter**, đường dẫn tài nguyên tĩnh, cơ chế fallback, cấu hình `@ApplicationPath`/`spring.jersey.application-path`, lựa chọn kiến trúc, bảo mật và các ca 404 khó chẩn đoán.

**Môi trường thực hành:** Java 17+, Maven, Spring Boot **3.5.16**, Spring MVC trên embedded Tomcat, Jersey 3.x dùng API `jakarta.ws.rs.*`. Project minh họa có **Jersey ở `/api/*`**, MVC ở `/mvc/*`, static HTML/CSS ở `/` và `/assets/*`, kiểm thử HTTP thật. Spring Boot 3.5.16 là bản OSS cuối của dòng 3.5 (phát hành 25/06/2026); triển khai production nên chọn nhánh hoặc gói bảo trì còn nhận security updates. Code được cố định version để học cú pháp Boot 3.5, không phải khuyến nghị giữ mãi một version hết hỗ trợ.

## 1. Ba hệ thống định tuyến khác nhau — phải tách bạch

Một Spring Boot web application có thể chứa nhiều Servlet, nhưng Servlet container không gọi tất cả Servlet để hỏi từng cái có muốn xử lý một URL hay không. Nó **chọn một Servlet theo URL pattern đã đăng ký**. Sau khi đã chọn:

- Nếu chọn **`DispatcherServlet`**, Spring MVC mới dùng các `HandlerMapping` để tìm `@Controller`, `@RestController`, `RouterFunction`, welcome page hoặc **static resource handler**.
- Nếu chọn **Jersey `ServletContainer`**, Jersey mới dùng JAX-RS model (`@Path`, `@GET`, `@Produces`, `@Provider`, ...) để tìm tài nguyên REST.
- Nếu **Jersey hoạt động ở chế độ Filter**, nó tham gia Servlet filter chain trước một Servlet phía sau; tùy cấu hình Jersey có thể tự trả response hoặc **chuyển tiếp** khi route Jersey không tồn tại.

~~~text
HTTP GET /assets/site.css
          │
          ▼
     Embedded Tomcat
          │
          │  [BƯỚC 1] Servlet URL mapping
          │
          ├──── /api/* ─────► Jersey ServletContainer
          │                      │
          │                      └── JAX-RS @Path/@GET matching
          │
          └──── / (default) ► Spring MVC DispatcherServlet
                                 │
                                 │ [BƯỚC 2] Spring HandlerMappings
                                 ├── @RestController / @GetMapping
                                 ├── WelcomePageHandlerMapping
                                 └── ResourceHttpRequestHandler
                                       │
                                       └── classpath:/static/assets/site.css
~~~

**Hệ quả quan trọng:** Một file tồn tại dưới `src/main/resources/static` không có nghĩa mọi HTTP request đến file ấy sẽ được Spring Boot tự phục vụ. Nếu Servlet container chọn Jersey trước, `DispatcherServlet` và `ResourceHttpRequestHandler` **không được gọi**. Jersey có thể trả 404 dù file CSS vẫn nằm đúng chỗ.

Trong bài này, “tài nguyên tĩnh” chủ yếu là HTML/CSS/JavaScript/ảnh/font ở classpath, **khác** khái niệm **JAX-RS resource**: một class có `@Path` nhận request REST. Hai thứ cùng gọi là “resource” nhưng do hai hệ thống khác nhau định tuyến.

## 2. Jersey là gì? Khác Spring MVC như thế nào?

**Jersey** là một implementation của **Jakarta RESTful Web Services (JAX-RS)**. Nó cung cấp HTTP API qua annotations thuộc `jakarta.ws.rs`. **Spring MVC** là web framework trong Spring, chạy Servlet API qua `DispatcherServlet` và các annotations `org.springframework.web.bind.annotation`.

| Khía cạnh | Jersey / JAX-RS | Spring MVC |
| --- | --- | --- |
| HTTP entry point điển hình | `org.glassfish.jersey.servlet.ServletContainer` (Servlet hoặc Filter) | `org.springframework.web.servlet.DispatcherServlet` |
| Đăng ký endpoint | `ResourceConfig#register`, `@Path`, `@GET`, `@POST` | `@Controller`/`@RestController` + `@GetMapping`/`@PostMapping` |
| URL base | `@ApplicationPath` hoặc `spring.jersey.application-path` | Servlet mapping, thường `/`; có thể có `spring.mvc.servlet.path` |
| Serialize response | JAX-RS `MessageBodyWriter` và providers | Spring `HttpMessageConverter` |
| Exception mapping | JAX-RS `ExceptionMapper` | Spring MVC `@ExceptionHandler`/`@ControllerAdvice` |
| Validation | Jakarta/Jersey integration theo providers | Spring MVC validation integration |
| Static file auto-serving | **Không** bằng cách chỉ đăng ký một JAX-RS resource | Spring MVC `ResourceHttpRequestHandler` qua Boot auto-config |
| Có thể dùng Spring beans? | **Có**, nếu tích hợp Jersey/Spring đúng | Mặc định Spring-managed controllers/services |

Cùng một HTTP method và URL có thể được **hai framework định nghĩa ở source code**, nhưng framework nào được gọi tùy **container mapping/Servlet filter chain**, không tự ưu tiên annotation theo tên.

### 2.1. Ví dụ cùng chức năng nhưng khác API

Jersey endpoint (mảnh code minh họa):

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/hello")
public class JerseyHelloResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "hello from Jersey\n";
    }
}
~~~

MVC endpoint tương đương:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SpringHelloController {
    @GetMapping(value = "/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "hello from MVC\n";
    }
}
~~~

**Hai snippet là lớp riêng để so sánh, chưa phải project runnable**. Với Jersey, còn cần `ResourceConfig` để register class và Servlet/Filter mapping. Với MVC, cần `DispatcherServlet`/Spring MVC web application. Khi cả hai lớp có path `/hello`, **container không tự cân nhắc JAX-RS @Path so với Spring @GetMapping để chọn “đúng” handler**. Cách dùng an toàn là tách namespaces.

### 2.2. Spring Bean trong Jersey

Spring Boot có native integration để Jersey resource class là `@Component` và có thể inject Spring services qua constructor/injection phù hợp. Để Jersey biết resource nào là endpoint, vẫn cần đăng ký nó trong `ResourceConfig` (ví dụ `register(HelloResource.class)`). **Component scanning của Spring không tự biến mọi `@RestController` thành Jersey resource**; ngược lại `@Path` không làm `DispatcherServlet` coi class đó như Spring MVC controller.

Nếu `@Component` được dùng ở Jersey resource, lifecycle và DI có thể do Spring quản lý; nhưng JAX-RS routing/converters/exception mappers vẫn thuộc Jersey. Không trộn `@GetMapping` với `@Path` rồi mong cả hai pipeline áp dụng chung lên một handler method.

## 3. Bước quan trọng nhất: Servlet URL mapping

Jakarta Servlet 6.0 specification đưa ra cách container chọn Servlet theo thứ tự tương đối:

1. **Exact path mapping:** ví dụ `/health`.
2. **Longest path-prefix mapping:** ví dụ `/api/*` phù hợp với URL dưới `/api/`.
3. **Extension mapping:** ví dụ `*.jsp`, khi không có exact/prefix phù hợp.
4. **Default mapping:** `/`, khi không có mapping ưu tiên hơn.

Ở Servlet spec, `/` và `/*` **không có cùng vai trò**:
- `/` là **default Servlet mapping**, phù hợp làm fallback cho phần còn lại khi không có mapping khác.
- `/*` là **path-prefix mapping rất rộng**, có thể chiếm hầu hết URLs trước Servlet có default mapping `/`.
- `/api/*` là path-prefix hẹp hơn, chỉ đưa URL tương ứng vào Jersey.

Trong Spring Boot Servlet application thông thường, `DispatcherServlet` được đăng ký ở **`/`**. Jersey khi dùng **Servlet mode mặc định** được Boot đăng ký với **`/*`**, trừ khi bạn cấu hình base path. Đây là lý do một app có cả MVC và Jersey mặc định có thể gặp 404 tĩnh.

### 3.1. So sánh hai mapping

~~~text
Cấu hình RỦI RO:
    Jersey ServletContainer  -> /*
    DispatcherServlet        -> /

GET /assets/site.css:
    mapping /* của Jersey được ưu tiên hơn "/" default.
    Jersey không có @Path("/assets/site.css") -> 404.
    MVC ResourceHttpRequestHandler không nhận request này.

Cấu hình TÁCH RÕ:
    Jersey ServletContainer  -> /api/*
    DispatcherServlet        -> /

GET /api/hello:
    /api/* -> Jersey @Path("/hello") -> 200.

GET /mvc/hello:
    /     -> DispatcherServlet -> Spring MVC controller -> 200.

GET /assets/site.css:
    /     -> DispatcherServlet -> static resource handler -> 200.
~~~

Với tách namespaces, đây là phân tuyến **trước khi** Spring MVC chọn controller/static resource. Một `@Order` trên `@Controller` hoặc `WebMvcConfigurer` không đổi được Servlet đã được Tomcat chọn.

### 3.2. URL nào thuộc ai trong mô hình đề xuất?

| Request path | Servlet được chọn | Handler dự kiến |
| --- | --- | --- |
| `GET /api/hello` | Jersey `/api/*` | JAX-RS resource `@Path("/hello")` |
| `GET /api/mvc/hello` | Jersey `/api/*` | 404 nếu không có JAX-RS route tương ứng; **không** thử MVC |
| `GET /mvc/hello` | `DispatcherServlet` ở `/` | Spring MVC `@GetMapping("/mvc/hello")` |
| `GET /assets/site.css` | `DispatcherServlet` | Spring MVC `ResourceHttpRequestHandler` |
| `GET /` | `DispatcherServlet` | Welcome page nếu có `static/index.html` |
| `GET /api/assets/site.css` | Jersey `/api/*` | Thường 404, dù file `static/api/assets/site.css` tồn tại |
| `GET /unknown` | `DispatcherServlet` | MVC static handler có thể kết thúc bằng `NoResourceFoundException`/404 |

**Không suy ra Java class đích chỉ từ đường dẫn URI**: phải kiểm tra runtime mapping. Một URL public còn có thể bị CDN, Nginx, gateway rewrite trước khi vào Tomcat.

### 3.3. `@ApplicationPath` và `spring.jersey.application-path`

Trong Spring Boot, cách ít thao tác nhất để đổi Jersey servlet mapping là annotate class cấu hình kế thừa `ResourceConfig`:

~~~java
import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
    }
}
~~~

Với Jersey servlet mode, mapping này theo thiết kế trở thành **`/api/*`**, còn `@Path("/hello")` bên trong được hiểu tương đối với **`/api`**. Vì vậy URL cuối là **`/api/hello`**, không phải `/api/api/hello`.

Có thể thay bằng property:

~~~properties
spring.jersey.application-path=/api
~~~

**Property này, nếu đặt, override `@ApplicationPath`** theo Spring Boot. Để tránh hai nguồn cấu hình cạnh tranh, chọn một phương án rõ ràng, ghi test mapping cuối. Nếu constructor `ResourceConfig` không có `@ApplicationPath` và không cấu hình property, Jersey servlet mặc định có thể đăng ký rộng `/*`.

**`spring.jersey.type=servlet`** là chế độ mặc định trên Boot 3.5; dùng property explicit trong project lab để dễ đọc. `@ApplicationPath` của Jakarta REST không thay `server.servlet.context-path` của toàn ứng dụng.

### 3.4. Context path và proxy prefix không giống Jersey base path

Giả sử có:

~~~properties
server.servlet.context-path=/portal
spring.jersey.application-path=/api
~~~

Khi đó Servlet context path thêm vào **mọi** route trong ứng dụng: Jersey thường nhận `/portal/api/hello`; MVC nhận `/portal/mvc/hello`; static nhận `/portal/assets/site.css`. Context path `/portal` không phải `@Path` của Jersey, cũng không phải `/api`.

Khi proxy public route `/shop/api/...` nhưng backend nhận `/api/...`, cần thêm thiết kế proxy rewrite/forwarded prefix; **không** tự đổi `@ApplicationPath("/shop/api")` trừ khi backend thực sự nhận đường đó. Nếu thấy 404, ghi **URI public và URI upstream**, vì không thể sửa Servlet mapping bằng cấu hình media type hay CORS.

## 4. Spring Boot phục vụ static resources như thế nào?

Khi Spring MVC được auto-configured và `DispatcherServlet` được chọn, Boot đăng ký static resource handlers thông qua `ResourceHttpRequestHandler`.

Các classpath locations mặc định bao gồm:

~~~text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
~~~

Ngoài ra Spring Boot có thể phục vụ file từ root của `ServletContext` theo cấu hình. Ví dụ:

~~~text
src/main/resources/static/index.html          -> GET /
src/main/resources/static/assets/site.css    -> GET /assets/site.css
src/main/resources/public/logo.svg           -> GET /logo.svg
src/main/resources/META-INF/resources/help.html -> GET /help.html
~~~

**Không** ghi đường `/static/` vào public URL chỉ vì directory tên `static`. Trong ví dụ, file nằm ở `classpath:/static/assets/site.css` thì path công khai là `/assets/site.css`, không phải `/static/assets/site.css`.

### 4.1. Resource handler không phải Tomcat default servlet

Spring Boot MVC **mặc định xử lý static qua Spring MVC handler**, không dựa vào default servlet của Tomcat. Embedded standalone application thường **không bật** default Servlet riêng của container theo thiết lập Boot.

Property:

~~~properties
server.servlet.register-default-servlet=true
~~~

cho phép bật container default servlet khi bạn có lý do đặc biệt và hiểu mapping của container. Nó **không** phải cách chữa đúng cho Jersey `/*` nuốt mọi URL: URL đã match Jersey có thể không bao giờ đến default servlet. Nếu ứng dụng chỉ có Jersey Filter và **không** có một servlet phía sau phục vụ requests không do Jersey bắt, bạn có thể cần default servlet; **nhưng nếu có DispatcherServlet**, nó là lựa chọn phía sau để xử lý MVC/static.

### 4.2. Hai nhóm cấu hình tĩnh dễ nhầm

~~~properties
# Mặc định MVC static handler thường mapped /**
spring.mvc.static-path-pattern=/**

# Ví dụ: chuyển URL tĩnh sang /resources/** thay vì /**.
# spring.mvc.static-path-pattern=/resources/**
~~~

`spring.mvc.static-path-pattern` thay **URL pattern**, không nhất thiết thay directory vật lý. Nếu file có path `classpath:/static/assets/site.css` và bạn đặt `/resources/**`, public URL sẽ thành **`/resources/assets/site.css`** khi handler mapping tương ứng được dùng.

~~~properties
# Ví dụ thay thế các classpath locations mặc định:
# spring.web.resources.static-locations=classpath:/assets/
~~~

`spring.web.resources.static-locations` thay **locations mà Spring tìm bytes**, không tự đổi public URL prefix. Với property này, bạn phải đặt file dưới `src/main/resources/assets/` thay vì mặc định `static` nếu không giữ các locations cũ trong list.

**Đừng cấu hình hai property rồi nhầm:** một cái đổi **URL**, một cái đổi **chỗ tìm file**. Và cả hai chỉ có tác dụng khi request được **DispatcherServlet/static handler** xử lý, không kéo một URL từ Jersey servlet sang MVC.

### 4.3. Vì sao một URL lạ có thể báo `NoResourceFoundException`?

Với mapping MVC static mặc định `/**`, Spring MVC có thể tìm thấy **resource handler phù hợp path**, dù **không có file**. Handler thử tìm file rồi đưa ra 404, thường là `NoResourceFoundException` trong Spring Framework mới. Vì vậy không phải mọi request MVC thiếu route đều ném `NoHandlerFoundException`.

Để phân biệt:
- Request **không bao giờ vào DispatcherServlet** → xem Servlet mappings/Jersey.
- Request vào MVC static handler nhưng **file không tồn tại** → xem classpath locations, build JAR, case-sensitive filename.
- Request vào MVC controller nhưng trả lỗi → xem controller/exception handler và HTTP method/content negotiation.

Điều chỉnh `spring.mvc.static-path-pattern` sang một prefix hẹp hoặc `spring.web.resources.add-mappings=false` có thể thay hành vi fallback trong MVC, nhưng **không tự khôi phục** quyền xử lý của MVC nếu Jersey đang chiếm path ở tầng Servlet.

### 4.4. Static index, cache và webjars

Nếu `src/main/resources/static/index.html` tồn tại, Boot MVC thường xem là **welcome page** ở `/` khi không có route khác ưu tiên hơn. Webjars được phục vụ qua `/webjars/**` nếu file JAR chứa resources đúng Webjar layout.

Cache/resource chain có thể được cấu hình qua `spring.web.resources.cache.*`, `spring.web.resources.chain.*` và `WebMvcConfigurer`. Tuy vậy việc tắt cache, xóa browser cache hay đổi tên file không giải quyết lỗi **Jersey servlet `/*` cướp URL static**. Đầu tiên phải xác nhận servlet nào nhận request; sau đó mới xử lý cache/versioning/MIME.

### 4.5. Đóng gói JAR và thư mục tĩnh

Khi build `spring-boot:repackage`, resources từ `src/main/resources/static` thường được đưa vào classpath của executable JAR, ví dụ dưới `BOOT-INF/classes/static`. Không bắt servlet container đọc file ở path `src/main/resources/...` ngoài process khi ứng dụng đã được đóng gói.

Không dùng `src/main/webapp` như địa chỉ static mặc định cho executable JAR: Spring Boot docs cảnh báo thư mục đó phù hợp WAR hơn và có thể bị bỏ qua trong JAR. Đối với content người dùng upload, **không** tự đặt dưới public static classpath directory; dùng storage và authorization riêng.

## 5. Spring Boot tự cấu hình Jersey như thế nào?

Khi có `spring-boot-starter-jersey` và **một** bean `ResourceConfig` hợp lệ, Boot cung cấp Jersey auto-configuration. Hai kiểu chính:

| Kiểu | Property | Spring Boot registration thông thường | Cơ chế |
| --- | --- | --- | --- |
| **Servlet** | `spring.jersey.type=servlet` (mặc định) | `ServletRegistrationBean` tên `jerseyServletRegistration` | URL được Servlet container route tới Jersey servlet; không tự fallback sang MVC |
| **Filter** | `spring.jersey.type=filter` | `FilterRegistrationBean` tên `jerseyFilterRegistration` | Jersey chạy trong filter chain; có thể forward sang Servlet phía sau nếu cấu hình |
| Filter order | `spring.jersey.filter.order` | Giá trị order cho Jersey filter | Chỉ có ý nghĩa ở filter mode |
| Servlet startup | `spring.jersey.servlet.load-on-startup` | Load-on-startup policy | Không phải order route/JAX-RS |
| Init parameters | `spring.jersey.init.*` | Params đưa vào Jersey Servlet/Filter | Chỉ dùng khi cần cấu hình Jersey |

`@Component public class JerseyConfig extends ResourceConfig` cũng được Spring xem như **một Bean** `ResourceConfig`. Không nhất thiết phải khai báo thêm một `@Bean ResourceConfig` khác, vì có thể tạo **nhiều ResourceConfig beans** ngoài ý muốn. Đăng ký REST classes rõ ràng:

~~~java
@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
        // register(MyExceptionMapper.class);
        // register(MyFeature.class);
    }
}
~~~

Đoạn này là **mảnh khái niệm**; imports và project đầy đủ có ở mục 6.

Nếu tùy biến nâng cao, có thể cung cấp `ResourceConfigCustomizer` hoặc custom registration beans theo contract Boot. Nhưng **đừng vừa giữ auto-registration mặc định vừa tự đăng ký một Jersey ServletContainer khác** trên cùng URL, dẫn đến mapping conflicts hoặc filter/servlet hoạt động lặp.

## 6. Project hoàn chỉnh: Jersey `/api/*` + Spring MVC `/mvc/*` + HTML/CSS tĩnh

Đây là cách phối hợp **đề xuất cho ứng dụng cần hai framework ở namespaces khác nhau**: để Jersey làm **Servlet** dưới `/api/*`, còn `DispatcherServlet` của Spring MVC là default `/`. Không cần Jersey Filter, không cần chỉnh order của Spring MVC, không cần bật Tomcat default servlet.

### 6.1. Cấu trúc thư mục

~~~text
jersey-mvc-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jerseymvcdemo/
    │   │   ├── DemoApplication.java
    │   │   ├── JerseyConfig.java
    │   │   ├── HelloResource.java
    │   │   └── MvcHelloController.java
    │   └── resources/
    │       ├── application.properties
    │       └── static/
    │           ├── index.html
    │           └── assets/site.css
    └── test/java/com/example/jerseymvcdemo/
        └── WebRoutingIntegrationTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>jersey-mvc-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jersey</artifactId>
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

Hai starters phục vụ **hai programming models**, Spring MVC và Jersey. Maven resolution sẽ quản lý các transitive dependencies phù hợp trong BOM của Boot. Không dùng `javax.ws.rs.*` trong Boot 3.5/Jersey 3.x; các annotations mới có namespace **`jakarta.ws.rs.*`**.

### 6.3. `src/main/java/com/example/jerseymvcdemo/DemoApplication.java`

~~~java
package com.example.jerseymvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.4. `src/main/java/com/example/jerseymvcdemo/JerseyConfig.java`

~~~java
package com.example.jerseymvcdemo;

import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
    }
}
~~~

**Vì sao `@ApplicationPath("/api")`?** Nó đổi Jersey Servlet mapping từ quá rộng `/*` thành `/api/*`, để các đường ngoài API có thể vào DispatcherServlet. `ResourceConfig#register` cho Jersey biết `HelloResource` là class xử lý HTTP. Không cần `ServletRegistrationBean` tự tạo vì Boot auto-register Jersey khi có ResourceConfig.

### 6.5. `src/main/java/com/example/jerseymvcdemo/HelloResource.java`

~~~java
package com.example.jerseymvcdemo;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.springframework.stereotype.Component;

@Component
@Path("/hello")
public class HelloResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "jersey-ok\n";
    }
}
~~~

Đây là **JAX-RS resource**, không phải Spring `@RestController`. URL thực là `/api/hello`, vì `/api` đến từ servlet base mapping và `/hello` là class-level JAX-RS path. `@Component` giúp Spring tích hợp lifecycle/DI; `register(HelloResource.class)` gắn endpoint vào Jersey.

### 6.6. `src/main/java/com/example/jerseymvcdemo/MvcHelloController.java`

~~~java
package com.example.jerseymvcdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MvcHelloController {

    @GetMapping(value = "/mvc/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "mvc-ok\n";
    }
}
~~~

Đây là Spring MVC controller được `DispatcherServlet` tìm qua `RequestMappingHandlerMapping`. Nó xử lý `/mvc/hello` khi container chọn Servlet mặc định `/`. Nếu bạn copy mapping này thành `/api/mvc/hello` mà vẫn giữ Jersey Servlet ở `/api/*`, endpoint MVC sẽ **không được gọi**, dù Spring có tìm thấy method trong ApplicationContext.

### 6.7. `src/main/resources/application.properties`

~~~properties
server.port=8080
spring.application.name=jersey-mvc-demo

# Explicit cho người đọc: Jersey chạy như Servlet.
spring.jersey.type=servlet

# Không cần đặt spring.jersey.application-path:
# @ApplicationPath("/api") trên JerseyConfig đã quy định base path.

# Giữ mặc định MVC servlet mapping "/" và static handlers.
# Không thêm @EnableWebMvc hoặc custom DispatcherServlet registration.
~~~

Nếu dùng property `spring.jersey.application-path=/api` thay annotation, **xóa annotation hoặc chấp nhận property override** và viết integration tests. Không đồng thời cho Jersey mapping quá rộng và trông chờ Spring MVC static handler tự giành lại các URL.

### 6.8. `src/main/resources/static/index.html`

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Jersey and MVC demo</title>
  <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
  <h1>Jersey and MVC demo</h1>
  <p>Servlet mapping chia Jersey va Spring MVC.</p>
  <ul>
    <li><a href="/api/hello">Jersey REST</a></li>
    <li><a href="/mvc/hello">Spring MVC</a></li>
  </ul>
</body>
</html>
~~~

Vì `index.html` nằm ở **classpath:/static** và Boot MVC có welcome-page support, `GET /` thường trả HTML này khi không có MVC controller xử lý root trước nó. CSS được tham chiếu bằng URL `/assets/site.css`, không phải `/static/assets/site.css`. Với context path hoặc reverse proxy prefix, cần dùng context-aware links; đường tuyệt đối trên đây chỉ nhằm minh họa lab root context.

### 6.9. `src/main/resources/static/assets/site.css`

~~~css
body {
  font-family: sans-serif;
  color: #246;
}
h1 {
  margin-bottom: 0.5rem;
}
~~~

File này được Spring MVC ResourceHttpRequestHandler phục vụ ở `GET /assets/site.css`, miễn DispatcherServlet được chọn. Không cần viết `@GetMapping("/assets/site.css")` cho static file.

### 6.10. Chạy ứng dụng

Tại root folder `jersey-mvc-demo`:

~~~bash
java -version
mvn spring-boot:run
~~~

Sau khi app khởi động trên port 8080, mở terminal khác:

~~~bash
curl -i http://localhost:8080/api/hello
curl -i http://localhost:8080/mvc/hello
curl -i http://localhost:8080/assets/site.css
curl -i http://localhost:8080/
curl -i http://localhost:8080/api/unknown
~~~

**Kết quả cần xác minh** (body controller được ghi rõ; toàn bộ HTTP headers có thể khác theo môi trường):

| Request | Status mong đợi | Nội dung/đường xử lý |
| --- | --- | --- |
| `GET /api/hello` | **200 OK** | Body `jersey-ok\n`, Jersey JAX-RS resource |
| `GET /mvc/hello` | **200 OK** | Body `mvc-ok\n`, Spring MVC controller |
| `GET /assets/site.css` | **200 OK** | CSS có `color: #246;`, MVC static handler |
| `GET /` | **200 OK** | HTML chứa `Jersey and MVC demo`, MVC welcome page |
| `GET /api/unknown` | **404 Not Found** | Jersey được chọn vì `/api/*`, không có JAX-RS endpoint |
| `GET /unknown` | **404 Not Found** | Không có MVC controller/static resource tương ứng |

**Quan trọng:** `curl -i` in cả headers, Date, Content-Type, Connection và encoding có thể khác phiên bản embedded server. Kỳ vọng các status/body trên là **kết quả thiết kế từ source**, không phải cam kết đã chạy trên mọi host. Các chuỗi `"jersey-ok\n"` và `"mvc-ok\n"` có newline cuối đúng như Java code.

Trong PowerShell có thể cần `curl.exe` nếu `curl` được alias thành `Invoke-WebRequest`. Trên Windows khi copy file text có CRLF, file CSS/HTML có thể có line ending khác so với code fence; không dùng raw byte equality cho CSS/HTML nếu chưa kiểm soát encoding/file creation.

### 6.11. Integration test với embedded server thật

File **`src/test/java/com/example/jerseymvcdemo/WebRoutingIntegrationTest.java`**:

~~~java
package com.example.jerseymvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebRoutingIntegrationTest {

    @LocalServerPort
    int port;

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    @Test
    void jerseyHandlesApi() {
        String body = RestClient.create().get()
                .uri(url("/api/hello")).retrieve().body(String.class);
        assertEquals("jersey-ok\n", body);
    }

    @Test
    void dispatcherServletHandlesMvc() {
        String body = RestClient.create().get()
                .uri(url("/mvc/hello")).retrieve().body(String.class);
        assertEquals("mvc-ok\n", body);
    }

    @Test
    void mvcServesStaticCss() {
        String body = RestClient.create().get()
                .uri(url("/assets/site.css")).retrieve().body(String.class);
        assertTrue(body.contains("color: #246;"));
    }

    @Test
    void mvcServesIndexWelcomePage() {
        String body = RestClient.create().get()
                .uri(url("/")).retrieve().body(String.class);
        assertTrue(body.contains("Jersey and MVC demo"));
    }

    @Test
    void unknownApiPathDoesNotBecomeMvcResource() {
        assertThrows(HttpClientErrorException.NotFound.class, () ->
                RestClient.create().get()
                    .uri(url("/api/unknown"))
                    .retrieve().toBodilessEntity());
    }
}
~~~

Chạy:

~~~bash
mvn test
mvn clean package
java -jar target/jersey-mvc-demo-0.0.1-SNAPSHOT.jar
~~~

**Vì sao dùng `RANDOM_PORT`?** Project này học **Servlet URL mappings** — cấu hình container. Test bằng MockMvc standalone có thể chỉ test Spring MVC handlers và **không** tái tạo Jersey Servlet registration thật. `@SpringBootTest(webEnvironment=RANDOM_PORT)` khởi động embedded container, nên request qua socket sẽ được route thật. Nếu dự án có CI/CD, nên chạy tests cả khi package thành executable JAR để đảm bảo static resources nằm trong classpath.

Nếu test 404 không có `HttpClientErrorException.NotFound` mà nhận 500 hoặc redirect, xem startup/exception configuration và response thực trước khi kết luận. Test này thể hiện contract **Jersey trả 404 cho URL trong namespace Jersey không có JAX-RS route**, không phải chẩn đoán mọi trạng thái HTTP có thể xảy ra trong ứng dụng production có security/gateway.

## 7. Phương án thứ hai: Jersey Filter để nhường đường cho Spring MVC

Tách Jersey Servlet vào `/api/*` là cách đơn giản. Nhưng một số hệ thống muốn **Jersey và MVC dùng chung namespace**, ví dụ Jersey thử xử lý request trước; nếu không có JAX-RS route thì MVC nhận phần còn lại. Với trường hợp đó, Spring Boot có hỗ trợ Jersey như một **Servlet Filter**, kèm tính năng của Jersey chuyển tiếp **404 không có body** sang phần sau filter chain.

### 7.1. Hai thay đổi cấu hình

**Thay đổi 1:** trong `application.properties` dùng:

~~~properties
spring.jersey.type=filter
~~~

**Thay đổi 2:** trong `ResourceConfig` bật:

~~~java
property(ServletProperties.FILTER_FORWARD_ON_404, true);
~~~

Import `org.glassfish.jersey.servlet.ServletProperties`. Theo Jersey 3.x javadoc, tính năng **`FILTER_FORWARD_ON_404` chỉ có ý nghĩa ở Filter mode**. Khi Jersey định trả **404 với entity body trống**, Jersey có thể chuyển request tới filter/servlet phía sau, đồng thời reset response status phù hợp để downstream xử lý. Nếu Jersey đã tạo response lỗi có **entity body**, không có bảo đảm fallback; và một JAX-RS endpoint matcher có thể đi vào business logic trước khi hệ thống quyết định 404.

### 7.2. Biến thể hoàn chỉnh của `JerseyConfig`

**Chỉ áp dụng khi muốn thử thay thế cấu hình ở mục 6**, không giữ đồng thời hai `JerseyConfig` classes. Để Jersey filter được áp dụng rộng và minh họa MVC/static fallback, hãy **bỏ `@ApplicationPath("/api")`** (đồng thời đảm bảo không đặt `spring.jersey.application-path=/api`). File `JerseyConfig.java` trong phương án Filter:

~~~java
package com.example.jerseymvcdemo;

import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.servlet.ServletProperties;
import org.springframework.stereotype.Component;

@Component
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
        property(ServletProperties.FILTER_FORWARD_ON_404, true);
    }
}
~~~

Properties thay cho servlet mode:

~~~properties
server.port=8080
spring.jersey.type=filter

# Không dùng spring.jersey.application-path=/api cho demo shared namespace.
# Chỉ áp dụng filter forwarding 404 nếu không có entity.
~~~

Khi đó, do không còn JAX-RS base `/api`, route Jersey `@Path("/hello")` xuất hiện ở **`GET /hello`**; URL `GET /api/hello` không còn là REST route trong phương án này. `GET /mvc/hello` và `GET /assets/site.css` **được thiết kế để rơi qua Jersey filter sang DispatcherServlet** khi Jersey không có endpoint tương ứng và trả trạng thái 404 không body. Trong khi đó, `GET /hello` do Jersey trả nội dung.

Test:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/mvc/hello
curl -i http://localhost:8080/assets/site.css
curl -i http://localhost:8080/
~~~

**Không giữ integration test `jerseyHandlesApi()` ở mục 6 nguyên vẹn khi chuyển sang biến thể filter**: expected path của Jersey đã đổi từ `/api/hello` sang `/hello`. Hãy chỉnh tests cùng cấu hình và kiểm tra route dispatch ở server thật.

### 7.3. Khi nào Filter tốt, khi nào Servlet tách namespace tốt?

| Tiêu chí | Jersey servlet `/api/*` | Jersey filter + `FILTER_FORWARD_ON_404` |
| --- | --- | --- |
| Quyền định tuyến | Container tách namespaces rõ | Jersey thử trước, rồi có thể nhường cho Servlet sau |
| Static file ngoài `/api` | MVC nhận trực tiếp | Có thể qua Jersey filter rồi forward tới MVC |
| Dễ audit path/security | **Cao** nếu namespaces rõ | Cần xét mọi rule fallback, 404 có/không body |
| Chi phí một static request | Không đi vào Jersey runtime | Có thể đi qua Jersey matcher trước |
| Khi Jersey không có endpoint | 404 trong namespace Jersey | Có thể chuyển tiếp nếu 404 không entity |
| Rủi ro endpoint overlap | Giảm vì tách prefix | Cao hơn nếu Jersey và MVC cùng có path |
| Cấu hình chính | `@ApplicationPath("/api")` hoặc property | `spring.jersey.type=filter` và `FILTER_FORWARD_ON_404=true` |
| Default servlet phía sau | Không cần nếu MVC xử lý static | Cần một Servlet xử lý request fall-through, thường là DispatcherServlet |

**Gợi ý kiến trúc:** Ưu tiên **Servlet mappings riêng** khi có thể. Chỉ chọn **Filter mode/fallback** khi thiết kế hệ thống cần chung namespace hoặc đang di trú endpoints từng bước và đã có test cho collision, auth và 404 semantics.

### 7.4. Bẫy: `FILTER_FORWARD_ON_404` không phải “chuyển mọi lỗi sang MVC”

Theo Jersey ServletProperties, chỉ có **404 response không có entity** phù hợp điều kiện mới forward. Nó **không** tự chuyển:
- 401/403 do Jersey authentication/authorization;
- 405 Method Not Allowed khi URI có resource nhưng method sai;
- 406/415 content negotiation/media type;
- 500 do exception;
- 404 do custom `ExceptionMapper` trả JSON error body;
- lỗi proxy đã trả response trước khi vào backend;
- URL không thuộc filter URL mapping nếu filter bị giới hạn prefix.

Không dùng fallback làm cách che lỗi bảo mật. Khi có cả Jersey và MVC với route trùng nhau, có thể xảy ra “Jersey 404 → MVC endpoint” ngoài dự đoán. Phải viết test khẳng định **route nào được phép rơi qua**, không chỉ test status cuối.

### 7.5. `FILTER_STATIC_CONTENT_REGEX` và filter path hạn chế

Jersey có `ServletProperties.FILTER_STATIC_CONTENT_REGEX` để chỉ định regex những paths cần giao cho Servlet engine thay vì để Jersey xử lý như REST resource. Đây là lựa chọn nâng cao, không nên tự sao chép regex `.*` sẽ vô hiệu hóa phần lớn Jersey. Tài liệu Jersey lưu ý regex được áp trên incoming servlet path phù hợp; cần thử theo context/base path thực.

Nếu static paths xác định được rõ, phương án đơn giản hơn thường là **giới hạn Jersey filter mapping vào `/api/*`** bằng `@ApplicationPath`/property, để asset URLs ngoài `/api` không đi qua filter. Khi đó vẫn cần hiểu điều kiện fallback cho các request trong `/api`; không ép ứng dụng chung namespace nếu không cần.

## 8. Default servlet, `DispatcherServlet` và static handler: trường hợp nào cần ai?

Một số hướng dẫn cũ khuyên bật container default servlet để serve static. Nhưng trong Spring Boot MVC hiện đại, có ba khái niệm khác nhau:

1. **`DispatcherServlet`:** Servlet của Spring MVC, nhận request theo Servlet mapping.
2. **`ResourceHttpRequestHandler`:** handler nội bộ của MVC, được DispatcherServlet gọi cho static file khi URL được map.
3. **Container default servlet:** Servlet do web container cung cấp để fallback phục vụ files từ ServletContext root khi cấu hình cần.

Trong executable Spring Boot JAR với MVC starter, số 1 + 2 thường đủ để phục vụ static classpath. Số 3 **không cần bật** chỉ để giải quyết Jersey 404 do `/*`.

### 8.1. Tại sao bật default servlet không giải cứu mapping `/*`?

Giả sử:

~~~text
Jersey Servlet      = /*
DispatcherServlet   = /
Tomcat default      = /  (không thể trùng mapping cùng context một cách vô tội vạ)
~~~

Servlet spec chỉ chọn servlet theo mapping; `/*` vẫn thắng default `/` đối với URL phù hợp. Hơn nữa, hai servlets **không thể tùy tiện có cùng URL pattern** trong cùng effective registration — có thể xung đột startup/registration. Vì vậy cách sửa cốt lõi là **tách Jersey path** hoặc chuyển Jersey sang **Filter với forwardOn404**, chứ không “bật thêm default servlet” rồi mong container gọi cả ba.

### 8.2. Khi Jersey Filter được dùng nhưng không có MVC Servlet

Nếu ứng dụng chủ yếu Jersey Filter, không khai báo DispatcherServlet hoặc servlet khác xử lý fall-through, thì forwardOn404 cần một Servlet phía sau. Spring Boot docs nêu có thể bật:

~~~properties
server.servlet.register-default-servlet=true
~~~

**Chỉ khi phù hợp mô hình không có Servlet khác nhận request**, không paste property này vào project MVC/Jersey mẫu ở mục 6. Bật default servlet không làm Jersey tự render JSP/Thymeleaf, không tạo Spring MVC `ResourceHttpRequestHandler`, và không biến classpath resources thành public nếu runtime không map chúng qua cấu hình đúng.

## 9. MVC auto-configuration: những lựa chọn dễ làm mất static handling

### 9.1. `@EnableWebMvc`

Trong Spring Boot MVC, auto-configuration có static mappings, message converters, welcome page và WebJars support. Nếu thêm `@EnableWebMvc` để “sửa route”, bạn có thể **chuyển sang tự quản lý MVC configuration**, làm mất nhiều Boot defaults nếu không khai báo lại handlers.

Khi cần tinh chỉnh static path, ưu tiên **`WebMvcConfigurer`** mà **không** gắn `@EnableWebMvc`:

~~~java
// Mảnh minh họa, không cần trong project mục 6.
@Configuration
class StaticConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/files/**")
                .addResourceLocations("classpath:/files/");
    }
}
~~~

Đây chỉ là mảnh code, cần imports `Configuration`, `WebMvcConfigurer`, `ResourceHandlerRegistry`. Và **nó chỉ chạy sau khi DispatcherServlet đã nhận request**; nếu Jersey `/*` đang nhận `/files/foo` thì thêm handler trên không cứu được.

### 9.2. `spring.web.resources.add-mappings=false`

~~~properties
spring.web.resources.add-mappings=false
~~~

Tắt các default static resource mappings của Boot MVC. Nếu trước đó CSS/JS được serve bởi `ResourceHttpRequestHandler` mà giờ 404, kiểm tra property này và custom `WebMvcConfigurer`. Tắt static mapping có thể phù hợp API-only deployments, nhưng không nên dùng chỉ để thay đổi status của route lạ khi app có frontend bundle.

### 9.3. Prefix cho MVC Servlet

Property `spring.mvc.servlet.path` có thể thay path prefix cho DispatcherServlet trong một số cấu hình. Tuy nhiên Boot 3.5 docs lưu ý **PathPatternParser matching không tương thích với việc đặt Servlet path prefix** theo cách này nếu chưa điều chỉnh strategy. Khi bạn muốn tách Jersey và MVC, **ưu tiên đặt Jersey dưới `/api/*` còn MVC ở `/`**, đơn giản hơn việc di chuyển cả DispatcherServlet và static handlers.

Nếu thật sự dùng `spring.mvc.servlet.path=/ui`, cần kiểm tra rằng static URLs cũng bị đổi namespace, app có context path/proxy rewrite không, và path-matching strategy có tương thích không. Đừng coi property `spring.mvc.servlet.path` là alias của `spring.jersey.application-path`.

### 9.4. Định tuyến từ reverse proxy

Một API gateway có thể chuyển public `/v1/api/hello` thành backend `/api/hello`, hoặc ngược lại. Nếu test trực tiếp backend pass nhưng public URL 404:
- xem URI mà container **thật sự nhận** sau rewrite;
- xác minh Servlet mapping của Jersey/MVC ở backend;
- xem `X-Forwarded-Prefix`, `Forwarded` và host/scheme ảnh hưởng URL generation, không quyết định tự động việc mapping lại backend path;
- kiểm tra Nginx `proxy_pass` có hoặc không có trailing slash; regex ingress rewrite rules;
- so response đến từ proxy, Jersey hay MVC qua logs/headers.

Không dùng response status 404 một mình để kết luận static file không tồn tại.

## 10. Bảo mật khi nhiều web frameworks cùng chạy

Dùng nhiều frameworks không tự cấp chung security policy. **Servlet filter chain** (ví dụ Spring Security `DelegatingFilterProxy` → `FilterChainProxy`) có thể bảo vệ HTTP requests trước khi chọn Jersey/MVC handler khi mapping của filter phủ đường tương ứng, nhưng điều đó **không tự bảo đảm** Jersey JAX-RS resource dùng đúng Spring MVC annotations và exception handling.

### 10.1. Chọn route security đúng theo namespace

Ví dụ ý tưởng policy:
- `/api/**`: JAX-RS resources, yêu cầu bearer token hoặc authN phù hợp.
- `/mvc/**`: MVC controllers, yêu cầu session hoặc role tùy nghiệp vụ.
- `/assets/**`: static JS/CSS công khai nếu là frontend static.
- `/actuator/**`: quản lý và bảo vệ theo policy nghiêm.

Cần kiểm tra **một SecurityFilterChain có matcher cụ thể** cho API và fallback chain áp dụng đúng cho các URLs còn lại. Nếu chỉ bảo vệ `/mvc/**` bằng `securityMatcher` rồi để `/api/**` ngoài mọi chain, Jersey endpoints có thể **không được Spring Security chặn**. Ngược lại, policy `anyRequest().authenticated()` có thể làm CSS/index trả 401 nếu không cho phép assets cần thiết.

### 10.2. Exception mapping của Jersey khác Spring MVC

Nếu Jersey method ném `jakarta.ws.rs.WebApplicationException` hoặc exception khác, Jersey dùng JAX-RS `ExceptionMapper`/`Response` semantics. Spring MVC `@RestControllerAdvice`/`@ExceptionHandler` thường **không** phải bộ xử lý toàn cục cho Jersey runtime.

Đừng đặt `@ControllerAdvice` trả JSON error rồi mong Jersey servlet tự dùng nó. Thiết kế consistent error contracts bằng `ExceptionMapper<Throwable>` trong Jersey và `@ControllerAdvice` trong MVC nếu cần; test HTTP behavior ở cả hai endpoints. Tránh mapper “catch all” nuốt lỗi bảo mật hoặc trả 200 cho exceptions.

### 10.3. Jersey + Spring Security method security

Spring Boot hướng dẫn, khi bảo vệ Jersey endpoints bằng Spring Security method-level rules, nên cấu hình Jersey dùng `setStatus` thay cho `sendError` để Spring Security có thể xử lý authentication/authorization failure trước khi response bị commit. Ví dụ mảnh cấu hình trong `ResourceConfig`:

~~~java
property("jersey.config.server.response.setStatusOverSendError", true);
~~~

Đây là **tùy chọn theo trường hợp security**, không phải yêu cầu bắt buộc của lab public endpoints. Không nhầm nó với `ServletProperties.FILTER_FORWARD_ON_404`: cái trước ảnh hưởng cách ghi HTTP status/error, cái sau là cơ chế fallback **chỉ trong filter mode**.

### 10.4. CORS và preflight

CORS là chính sách browser origin, không phải Servlet mapping. MVC `WebMvcConfigurer#addCorsMappings` áp trên MVC routing; nó **không tự cấu hình Jersey resource** giống hệt. Jersey có response filters hoặc CORS feature riêng, và Spring Security có `http.cors(...)` trước authorization nếu tích hợp. Khi coexist:
- xác định một nơi chịu trách nhiệm CORS headers với allowlist origins;
- test `OPTIONS` cho cả `/api/**` và `/mvc/**`;
- tránh hai filters cùng set `Access-Control-Allow-Origin` và headers trùng/xung đột;
- không lấy việc `curl` GET pass làm bằng chứng browser CORS/preflight pass;
- nếu có session/cookie, CSRF và SameSite policy độc lập với framework routing.

### 10.5. Static directory không dành cho dữ liệu riêng tư

Bất kỳ file nào đặt vào public static locations và được MVC resource handler expose đều có thể được GET bởi client nếu routing/security cho phép. **Không** đặt user uploads chứa dữ liệu riêng, backup config, secrets hoặc file nhạy cảm vào `src/main/resources/static`. Jersey namespace không bảo vệ static assets bên ngoài `/api`; phải thiết kế authorization/file-serving riêng.

### 10.6. Tránh route collision và API bypass

Khi đổi từ Jersey Servlet `/api/*` sang Jersey Filter `/*` + forwardOn404, một URL trước đây trả 404 có thể **rơi vào MVC route** có hành vi khác. Nếu hệ thống dùng 404 để ẩn endpoints hoặc bảo vệ tài nguyên theo namespace, fallback có thể làm phát sinh đường truy cập không mong muốn. Phải test authorization, method, media type và 404 semantics trước khi migration.

## 11. Quan sát runtime: request thực sự vào Servlet nào?

### 11.1. Kiểm tra Servlet registrations

Có thể dùng `ServletContext#getServletRegistrations()` để xem mappings của các Servlets đã đăng ký. Mảnh code **chẩn đoán, không thuộc project runnable mục 6**:

~~~java
@Bean
ApplicationRunner printServletMappings(ServletContext context) {
    return args -> context.getServletRegistrations().forEach((name, reg) ->
        System.out.println("SERVLET " + name
                + " class=" + reg.getClassName()
                + " mappings=" + reg.getMappings()));
}
~~~

Imports cần `jakarta.servlet.ServletContext`, `org.springframework.boot.ApplicationRunner` và `org.springframework.context.annotation.Bean`, đặt method trong Spring `@Configuration` class. Chỉ bật ở môi trường dev/staging đã kiểm soát; không public endpoint debug tiết lộ mappings.

Kết quả mong muốn của Servlet mode rõ prefix:
- Một servlet liên quan `DispatcherServlet` với mapping `/`.
- Một servlet liên quan Jersey `ServletContainer` với mapping `/api/*` (tên container-generated có thể khác).
- Không có hai registration cùng URL pattern vô ý.
- Trong Jersey Filter mode, Jersey xuất hiện ở **filter registrations**, không phải thứ hai là servlet Jersey nữa.

### 11.2. Kiểm tra mapping mà request được gán

Từ Servlet 4.0+, `HttpServletRequest#getHttpServletMapping()` giúp xem kết quả URL mapping của request. Ví dụ MVC controller **mảnh chẩn đoán**:

~~~java
@GetMapping("/debug/servlet")
@ResponseBody
public String servletMapping(HttpServletRequest request) {
    var m = request.getHttpServletMapping();
    return m.getServletName() + " pattern=" + m.getPattern()
            + " match=" + m.getMappingMatch();
}
~~~

Đặt method trong một `@Controller` có imports tương ứng. Endpoint này **chỉ chạy khi MVC được chọn**, nên nếu muốn quan sát Jersey servlet tương tự phải dùng JAX-RS `@Context HttpServletRequest` trong Jersey resource hoặc Servlet filter đo trước router. Đừng để debug route ở production vì nó có thể tiết lộ cấu trúc nội bộ.

### 11.3. Log filters, DispatcherServlet và Jersey

Tạm bật log trong staging:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.resource=TRACE
logging.level.org.glassfish.jersey=INFO
~~~

Cần đọc thực tế chứ không suy ra “Jersey log 404” = “MVC static không có file”. Đặt correlation ID, ghi request URI, Servlet mapping (dev-only), selected handler/status. Spring Boot Actuator `/actuator/mappings` có thể hỗ trợ xem Servlet/MVC mappings tùy version và exposure, nhưng **không thay test qua container**; bảo vệ Actuator trước public access.

### 11.4. DevTools và browser cache làm nhiễu

Ở development, sửa file static trong IDE nhưng không thấy thay đổi có thể liên quan resource copying, DevTools restart, build output hoặc cache. Trước khi đổi Jersey config:
1. Gọi trực tiếp `curl -i` URL tĩnh.
2. Kiểm tra source file tồn tại đúng `src/main/resources/static`.
3. Kiểm tra file đã được copy vào `target/classes/static` hoặc packaged JAR.
4. Kiểm tra mapping để biết request vào DispatcherServlet hay Jersey.
5. Sau đó mới xem browser/CDN cache và cache headers.

Nếu `curl -i /assets/site.css` trả Jersey error body, dù file static có trong JAR, đó là dấu hiệu rất mạnh URL vào Jersey Servlet quá rộng.

## 12. Bảng triệu chứng, nguyên nhân và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `GET /api/hello` 404 | ResourceConfig không register resource; base path sai; class annotation sai | Xem `@ApplicationPath`/property override, `@Path`, Jersey startup log |
| `GET /assets/site.css` 404 chỉ sau khi thêm Jersey | Jersey Servlet mặc định `/*` chiếm URL | Map Jersey thành `/api/*` hoặc chọn Filter + forwardOn404 |
| `GET /mvc/hello` 404 trong khi controller tồn tại | Container chọn Jersey hoặc MVC bị tắt/mapping khác | Xem Servlet registrations và effective URI |
| `GET /` không render `index.html` | Jersey `/*`, thiếu static file, MVC auto-config thay đổi | Xem servlet mapping trước; rồi file/WelcomePageHandlerMapping |
| `GET /static/assets/site.css` 404 | Đưa tên physical directory vào URL | Dùng `/assets/site.css` |
| Jersey API chạy nhưng HTML/CSS không | API routing Jersey ổn, MVC static không nhận URL | Tách Jersey prefix; test direct /assets |
| Static file có trong JAR nhưng 404 | Servlet chọn Jersey, static mappings disabled, hoặc sai public path | Xem mapping, `add-mappings`, path pattern |
| `NoResourceFoundException` trong MVC | ResourceHttpRequestHandler match path nhưng không tìm file | Kiểm tra classpath, spelling/case, handler locations |
| `NoHandlerFoundException` khác kỳ vọng | Static mapping không catch path hoặc MVC config khác | Xem handler mappings và `static-path-pattern` |
| Jersey method `@GET` không chạy | Register thiếu, wrong base path, media type/method hoặc router không chọn Jersey | Xem route/JAX-RS providers, GET/POST, Accept |
| MVC `@ControllerAdvice` không xử lý lỗi Jersey | Hai exception pipelines khác nhau | Jersey `ExceptionMapper` và MVC advice riêng |
| `@EnableWebMvc` làm static biến mất | Boot MVC auto-config không còn | Bỏ `@EnableWebMvc` nếu không muốn tự cấu hình toàn bộ |
| `spring.web.resources.add-mappings=false` | Tắt MVC default static handler | Bật mappings hoặc tự register resources |
| `spring.mvc.static-path-pattern=/resources/**` nhưng vẫn gọi `/assets/...` | URL tĩnh đã được remap | Gọi `/resources/assets/...` |
| Filter mode fallback vẫn 404 | `FILTER_FORWARD_ON_404` chưa bật; Jersey error có body; downstream không có Servlet | Check config, entity-less 404, DispatcherServlet/default servlet |
| Jersey 405 thay vì MVC GET | Container đã chọn Jersey nhưng method không hợp lệ | Sửa JAX-RS routes; Filter forwardOn404 không xử lý 405 |
| CORS GET được nhưng OPTIONS lỗi | Security/Jersey/MVC CORS settings khác nhau | Test preflight từng route và CORS headers cuối |
| Actuator 404 khi Jersey được thêm | Jersey `/*` bắt `/actuator/**` hoặc management path đổi | Check mappings và actuator exposure/security |
| OAuth callback/redirect sai prefix | Proxy rewrite/context path không nhất quán | So public URI, upstream URI, context path, forwarded headers |
| Test MockMvc pass nhưng JAR 404 static | MockMvc không tái tạo Servlet container/Jersey mapping | Dùng RANDOM_PORT integration test |
| Lúc nâng version Jersey gặp `javax.ws.rs`/`jakarta.ws.rs` mismatch | Dùng API namespace cũ | Boot 3.x/Jersey 3.x dùng `jakarta.ws.rs.*` |
| Có hai Jersey resources được xử lý ngoài ý muốn | Duplicate registration, class scanning + manual register, providers | Một ResourceConfig nhất quán, kiểm tra startup |

### 12.1. Debug có thứ tự, tránh sửa nhầm tầng

1. Ghi `GET path` thực tế **ở Tomcat** sau ingress rewrite, HTTP method, Accept và status.
2. Liệt kê **Servlet URL mappings** của DispatcherServlet và Jersey; xem request có rơi vào Jersey `/*` ngoài ý muốn không.
3. Nếu vào Jersey: kiểm tra `ResourceConfig` registration, `@ApplicationPath`, `spring.jersey.application-path` override, JAX-RS method/media type và Jersey exception mappers.
4. Nếu vào MVC: kiểm tra `@GetMapping`, `WelcomePageHandlerMapping`, `ResourceHttpRequestHandler`, static locations, `spring.web.resources.add-mappings`, `spring.mvc.static-path-pattern`.
5. Nếu dùng Jersey Filter: kiểm tra `spring.jersey.type=filter`, filter order, URL pattern, `FILTER_FORWARD_ON_404` và điều kiện 404 không body.
6. So kết quả local server `curl -i` với public gateway URL; nếu khác, xem proxy rewrite/cache.
7. Test `/api/hello`, `/mvc/hello`, `/assets/site.css`, `/` và những đường 404 cụ thể.
8. Đối chiếu routes security/CORS/CSRF, đặc biệt khi endpoint API không được Spring Security protect hoặc asset bị 401.
9. Test đóng gói bằng `mvn clean package` rồi `java -jar`, không chỉ dev mode.
10. Chốt regression tests trước khi di trú URL base hoặc đổi Jersey Servlet ↔ Filter.

## 13. Những anti-pattern nên tránh

**Anti-pattern 1 — Jersey `/*` rồi tăng order MVC controller.** Servlet container đã định tuyến tới Jersey; MVC `@Order`/`@GetMapping` không giành lại được. Sửa mapping Jersey.

**Anti-pattern 2 — Để Jersey và MVC cùng sở hữu `/api/hello` rồi trông chờ “framework sẽ tự chọn đúng”.** Việc chọn Servlet/Filter trước, handler route sau. Thiết kế API owner rõ ràng; nếu migration, có fallback policy và test.

**Anti-pattern 3 — Bật `server.servlet.register-default-servlet=true` như một lời giải vạn năng.** Default servlet không thắng Jersey `/*`. Có thể tạo vấn đề khác về file exposure/registration. Chỉ dùng khi kiến trúc cần Servlet fallback và biết hậu quả.

**Anti-pattern 4 — Tạo custom `ServletRegistrationBean<ServletContainer>` nhưng quên Boot đã auto-register Jersey.** Dễ trùng mapping hoặc hai instances. Dùng `@ApplicationPath`/property trước; override registration chỉ khi có yêu cầu được hiểu rõ.

**Anti-pattern 5 — Dùng `@EnableWebMvc` chỉ để sửa static 404.** Boot MVC resource configuration có thể bị thay; cần biết 404 đến từ Jersey hay MVC trước khi tự quản lý toàn bộ MVC.

**Anti-pattern 6 — Trộn `javax.ws.rs.*` và `jakarta.ws.rs.*`.** Spring Boot 3.5/Jersey 3.x dùng Jakarta namespace; code tham khảo Jersey 2.x/Boot 2.x có thể không compile đúng.

**Anti-pattern 7 — Nghĩ `spring.mvc.static-path-pattern=/assets/**` kéo file từ Jersey về MVC.** Property này chỉ điều chỉnh URL mappings của static handler **nếu request đã vào DispatcherServlet**.

**Anti-pattern 8 — Bật Filter fallback nhưng quên response body của Jersey 404.** `FILTER_FORWARD_ON_404` chỉ chuyển tiếp trường hợp phù hợp với contract; custom `ExceptionMapper` có thể khiến fallback không xảy ra.

**Anti-pattern 9 — Public toàn bộ `classpath:/static/` để phục vụ tài liệu riêng.** Static handler phục vụ tài nguyên tĩnh công khai theo security/routing; file chứa secret cần storage + authorization riêng.

**Anti-pattern 10 — Chỉ test controller bằng Mockito/MockMvc standalone rồi coi servlet routes đã đúng.** Đây là vấn đề URL routing của Servlet container; dùng integration test chạy embedded Tomcat/JAR và qua proxy nếu có.

## 14. Checklist triển khai và nâng cấp

| Kiểm tra | Điều kiện đạt |
| --- | --- |
| Kiến trúc | Có lý do rõ dùng Jersey thay vì MVC hoặc cùng tồn tại |
| Namespace | Jersey Servlet được giới hạn (ví dụ `/api/*`) hoặc Filter fallback có contract chính thức |
| MVC | DispatcherServlet mapping còn đúng (thường `/`), không bị Jersey `/*` chiếm |
| JAX-RS | Một ResourceConfig đăng ký đúng `@Path`/providers; `@ApplicationPath`/property nhất quán |
| Static | HTML/CSS/JS có trong classpath JAR ở locations đúng và path public đúng |
| Welcome | `GET /` trả `index.html` hoặc MVC controller như thiết kế |
| 404 semantics | Jersey 404, MVC missing handler và MVC static NoResourceFound được phân biệt |
| Filter fallback | `spring.jersey.type=filter` + `FILTER_FORWARD_ON_404` được test cho 404 không body; không giả định mọi lỗi đều forward |
| Security | Servlet filters bảo vệ cả API Jersey/MVC; allowed asset paths và Actuator được khai báo |
| Exceptions | Jersey `ExceptionMapper` và MVC `@ControllerAdvice` không bị hiểu là một pipeline |
| CORS/CSRF | Preflight, authentication và cross-origin được test trên cả các URL namespaces |
| Proxy | Public path, backend URI, context path, forwarded prefix khớp |
| Startup | Không duplicate servlet/filter registration, không mapping conflicts |
| Test | `@SpringBootTest(RANDOM_PORT)` và `java -jar` verify Jersey + MVC + static + 404 |
| Operations | Có logs/metrics, readiness, patch management và rollout không làm hỏng routes |

Một kiến trúc rõ namespaces thường dễ maintain hơn Filter fallback khi số route lớn hoặc cần audit bảo mật chặt. Nhưng Filter fallback vẫn hữu ích khi di trú endpoint giữa Jersey và MVC theo từng giai đoạn, miễn fallback semantics và test coverage được thiết kế trước.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một class Jersey có `@Path("/hello")` không phải là Spring MVC `@RestController`?
2. `DispatcherServlet` và `ResourceHttpRequestHandler` có cùng cấp trong Servlet container không?
3. Trong Servlet mapping, `/*` và `/` khác gì nhau?
4. Khi Jersey mặc định `/*`, tại sao `GET /assets/site.css` có thể 404 dù file ở `static/assets`?
5. Cách cấu hình Jersey Servlet nhận `/api/*` thay vì `/*` là gì?
6. `spring.jersey.application-path` có override `@ApplicationPath` không?
7. Khi Jersey `/api/*` và MVC `/`, ai xử lý `GET /mvc/hello`?
8. Trong ví dụ, URL của file `src/main/resources/static/assets/site.css` là gì?
9. Nếu đổi `spring.mvc.static-path-pattern=/resources/**` mà giữ file cũ, URL sẽ thay thành gì?
10. `spring.web.resources.static-locations` và `spring.mvc.static-path-pattern` thay đổi cùng một thứ không?
11. Vì sao `server.servlet.register-default-servlet=true` không tự khắc phục Jersey `/*`?
12. `spring.jersey.type=filter` có tác dụng gì khác `servlet`?
13. `ServletProperties.FILTER_FORWARD_ON_404` yêu cầu Jersey phản hồi có điều kiện gì?
14. Nếu Jersey trả 404 JSON body, có chắc MVC được gọi khi Filter mode bật fallback không?
15. Trong Spring Boot MVC, class nào phục vụ tệp static và nó nằm ở bước routing nào?
16. `@EnableWebMvc` có thể làm mất hỗ trợ static mặc định của Boot ra sao?
17. Vì sao `@ControllerAdvice` của MVC không mặc nhiên xử lý Jersey resource exceptions?
18. `securityMatcher("/api/**")` và path Servlet Jersey `/api/*` có quan hệ gì? Chúng có tự đảm bảo endpoint được bảo vệ không?
19. Tại sao `@SpringBootTest(RANDOM_PORT)` đáng tin hơn MockMvc standalone cho thử nghiệm này?
20. Nếu `/api/hello` hoạt động nhưng `/actuator/health` 404 sau khi thêm Jersey, bạn kiểm tra tầng nào trước?
21. Khi di chuyển Jersey servlet sang Filter, vì sao URL `/api/hello` có thể đổi thành `/hello` trong biến thể lab?
22. Có nên đặt user uploads private vào `src/main/resources/static` để Jersey kiểm tra quyền trước không?
23. Khi có reverse proxy rewrite public URL, bạn cần ghi lại những path nào để debug?
24. Mọi method `@GET` của Jersey có được `@GetMapping` của Spring MVC tìm thấy không?
25. Một request `GET /api/not-found` có bao giờ tự “thử” DispatcherServlet nếu Jersey đã chọn Servlet `/api/*` không?

**Đáp án ngắn:** (1) Hai programming models, hai runtimes. (2) Không, resource handler nằm **trong** MVC DispatcherServlet. (3) Path-prefix bắt rộng vs default servlet mapping. (4) Servlet container chọn Jersey nên MVC static handler không chạy. (5) `@ApplicationPath("/api")` hoặc `spring.jersey.application-path=/api`. (6) Có. (7) MVC DispatcherServlet. (8) `/assets/site.css`. (9) `/resources/assets/site.css`. (10) Không: locations vs URL pattern. (11) Không thắng prefix mapping `/*`. (12) Chạy trong Filter chain và có thể forward xuống Servlet. (13) Jersey 404 **không entity body**. (14) Không. (15) `ResourceHttpRequestHandler` khi DispatcherServlet được chọn. (16) Vô hiệu nhiều MVC auto-config defaults khi tự quản lý. (17) Jersey dùng `ExceptionMapper`. (18) Security filter chain phải match đúng và có authorization policy. (19) Test real Servlet mappings. (20) Kiểm tra `/*` Jersey và Actuator/MVC mappings. (21) Đã bỏ base `@ApplicationPath("/api")`. (22) Không, dùng authorized storage. (23) Public URI, upstream URI, servlet context path, Jersey base path và proxy prefix. (24) Không. (25) Không, trừ khi bạn thiết kế **Filter** với fallback; Servlet không tự thử.

## 16. Nguồn tài liệu chuẩn

- **Spring Boot 3.5 — Servlet Web Applications**, Spring MVC static content, welcome page, JAX-RS/Jersey auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- **Spring Boot 3.5 — How-to: Jersey**, cách dùng Jersey alongside another web framework và security `setStatusOverSendError`: https://docs.spring.io/spring-boot/3.5/how-to/jersey.html
- **Spring Boot 3.5 — Common Application Properties**, `spring.jersey.application-path`, `spring.jersey.type`, `spring.jersey.filter.order`, `spring.mvc.static-path-pattern`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- **Jakarta Servlet 6.0 Specification, Chapter 12**, URL mapping: exact, path-prefix, extension và default: https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html
- **Jersey 3.x ServletProperties API**, `FILTER_FORWARD_ON_404`/`FILTER_STATIC_CONTENT_REGEX`: https://eclipse-ee4j.github.io/jersey.github.io/apidocs/latest3x/jersey/org/glassfish/jersey/servlet/ServletProperties.html
- **Spring Framework MVC static resources**, resource handlers và pipeline: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html
- **Spring Framework DispatcherServlet**, request processing/HandlerMapping: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html
- **Spring Boot 3.5.16 System Requirements**, Java 17+ và Tomcat Servlet 6.0: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- **Spring Boot 3.5.16 release announcement**, ending OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
