# Jersey và JAX-RS như lựa chọn xử lý HTTP thay cho Spring MVC trong Spring Boot

Spring Boot thường được học cùng Spring MVC: HTTP request đến DispatcherServlet, được định tuyến vào @RestController, rồi trả JSON thông qua HttpMessageConverter. Nhưng Spring Boot không bắt buộc dùng Spring MVC để xây dựng REST API. Khi muốn dùng lập trình REST theo đặc tả **Jakarta RESTful Web Services (trước đây gọi là JAX-RS)**, bạn có thể lựa chọn **Jersey**, một implementation của đặc tả đó. Jersey có bộ định tuyến resource, providers, exception mappers và servlet riêng, được Spring Boot tự đăng ký khi cấu hình đúng.

Bài thuộc **Spring Boot - web-runtime → Mở rộng nền tảng web**. Phần thực hành sử dụng **Java 17, Spring Boot 3.3.13, Jersey 3.x, Maven và embedded Tomcat**. Toàn bộ mã trong project chính sử dụng package Jakarta **jakarta.ws.rs.*** phù hợp Spring Boot 3; package **javax.ws.rs.*** thường thuộc thế hệ Jersey/JAX-RS cũ và không nên trộn.

Trọng tâm là hiểu **cách chọn Jersey thay Spring MVC**, cấu hình **ResourceConfig**, xử lý route/status/JSON, dùng Spring dependency injection, kiểm thử servlet thật thay vì chỉ MockMvc, tránh xung đột servlet mapping và giới hạn package scanning trong executable JAR/WAR.

## 1. Mục tiêu và kiến thức đầu vào

Sau bài này, bạn có thể:

1. Phân biệt **Jakarta REST/JAX-RS là specification**, **Jersey là implementation**, **Spring MVC là một web framework khác**, còn **Spring Boot cung cấp auto-configuration/embedded runtime**.
2. Dùng **@Path, @GET, @POST, @PathParam, @QueryParam, @DefaultValue, @Produces, @Consumes, @Context** để viết HTTP resource.
3. Tạo Spring Boot Jersey REST project với **spring-boot-starter-jersey**, **ResourceConfig** và resource có **@Component**.
4. Giải thích vì sao **register(MyResource.class)** an toàn hơn package scan bằng packages(...) khi chạy executable archives.
5. Phân biệt Jersey servlet mặc định **/*, @ApplicationPath, spring.jersey.application-path, server.servlet.context-path**, cũng như servlet mode với filter mode.
6. Tạo responses JSON với status 200, **HTTP 201 Created**, 400, 404 và **Location**; map business error bằng **ExceptionMapper**.
7. Viết integration test dùng **@SpringBootTest(RANDOM_PORT) + Java 17 HttpClient** để chạy đường Servlet/Jersey thật.
8. Hiểu ranh giới giữa MVC HandlerMapping/ControllerAdvice/HttpMessageConverter và Jersey resource/provides/provider.
9. Biết cách dùng Spring Security, CORS, validation, observations và OpenAPI khi ứng dụng chạy Jersey.
10. Chọn Jersey hay MVC dựa trên nhu cầu thực tế, không dựa trên khẳng định hiệu năng thiếu đo đạc.

Nền tảng cần biết: Java 17, Spring Boot Maven, JSON, HTTP status/method, REST, Dependency Injection và embedded Servlet container.

## 2. Jersey, JAX-RS và Spring MVC khác nhau như thế nào?

### 2.1. Những tầng thường bị nhầm

| Thành phần | Trách nhiệm | API ví dụ |
| --- | --- | --- |
| **Jakarta REST (JAX-RS)** | Đặc tả REST programming model, annotation, context/provider API | jakarta.ws.rs.Path, GET, POST, Response |
| **Jersey** | Implementation thực thi Jakarta REST | org.glassfish.jersey.server.ResourceConfig |
| **Spring MVC** | Web framework của Spring cho Servlet stack | RestController, RequestMapping, DispatcherServlet |
| **Spring Boot** | Tự cấu hình dependency, web server, lifecycle và beans | SpringBootApplication, starter-jersey |
| **Servlet container** | HTTP connector, request/response, filters và servlet lifecycle | Tomcat, Jetty, Undertow |
| **Spring Security** | Authentication/authorization ở Servlet filters và method layer | SecurityFilterChain, method security |

Sơ đồ luồng:

~~~text
Browser / curl / HTTP client
              |
              v
Embedded Tomcat / Servlet container
              |
              +-- Servlet Filter chain (security, logging, etc.)
              |
              +-- Jersey Servlet (JAX-RS path)
              |     +-- ResourceConfig registration
              |     +-- @Path resources / @GET / @POST
              |     +-- JSON providers / ExceptionMapper
              |
              +-- Spring MVC DispatcherServlet (nếu sử dụng MVC)
                    +-- @RestController / @GetMapping
                    +-- HandlerMapping / HttpMessageConverter
~~~

Jersey và MVC có thể cùng ở một JVM, nhưng **chúng không dùng chung endpoint routing pipeline**. Một class Jersey @Path không tự biến thành controller của DispatcherServlet. Ngược lại, @RestController không tự trở thành JAX-RS resource của Jersey khi không được đăng ký.

### 2.2. JAX-RS là đặc tả, Jersey là runtime

Jakarta REST định nghĩa annotation HTTP methods, parameter binding, resource paths, Response, providers, request filters và exception mapping. Jersey triển khai những quy tắc đó: nhận request từ Servlet, chọn resource method phù hợp, xử lý body, gọi method và tạo response.

Jersey không phải triển khai duy nhất: Apache CXF và những implementation khác cũng có thể cung cấp JAX-RS. Spring Boot có **starter và auto-configuration trực tiếp cho Jersey**, còn với những implementation khác có thể cần cấu hình servlet/filter riêng.

### 2.3. Vì sao Jakarta namespace rất quan trọng?

Spring Boot 3 dựa trên Jakarta EE API với các package **jakarta.servlet.*** và **jakarta.ws.rs.***. Ứng dụng JAX-RS đời cũ có thể đang import **javax.ws.rs.Path** hoặc extension Jersey 2. Những annotation/type ở hai namespace **khác nhau**, dù tên class giống. Nếu nâng từ Boot 2/Jersey 2 sang Boot 3/Jersey 3, phải nâng tất cả JAX-RS imports, extensions, validation provider và dependencies liên quan.

~~~java
// Spring Boot 3 / Jersey 3: đúng namespace.
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;
~~~

Không nên thêm cả javax.ws.rs-api lẫn jakarta.ws.rs-api để “chữa” ClassNotFoundException mà chưa hiểu compatibility; điều đó thường làm hỗn loạn classpath.

### 2.4. So sánh annotation nhanh

| Yêu cầu | Spring MVC | Jakarta REST/Jersey |
| --- | --- | --- |
| Class xử lý HTTP | @RestController | @Path |
| GET | @GetMapping | @GET |
| POST | @PostMapping | @POST |
| URL path variable | @PathVariable | @PathParam |
| Query string | @RequestParam | @QueryParam, @DefaultValue |
| Header request | @RequestHeader | @HeaderParam |
| Cookie request | @CookieValue | @CookieParam |
| Body JSON | @RequestBody | Parameter + @Consumes + MessageBodyReader |
| Body JSON response | Return POJO/ResponseEntity | Return POJO/Response + MessageBodyWriter |
| Status/header | ResponseEntity | jakarta.ws.rs.core.Response |
| Media type | consumes/produces của mapping | @Consumes / @Produces |
| Exception mapping | @ControllerAdvice / @ExceptionHandler | ExceptionMapper / @Provider |
| Request filter | HandlerInterceptor, Servlet Filter | ContainerRequestFilter, Servlet Filter |
| Context | HttpServletRequest, Model | @Context UriInfo, HttpHeaders, SecurityContext |
| Dependency injection | Spring beans | Spring integration hoặc HK2/Jersey |
| Test web runtime | MockMvc hoặc random port | Real HTTP / Jersey test framework, random port |

**Không tự chuyển @ControllerAdvice thành một annotation trên Jersey mà mong framework hiểu**: nó thuộc cơ chế MVC. Với Jersey, dùng ExceptionMapper và đăng ký provider.

## 3. Chọn Jersey hay Spring MVC?

### 3.1. Những lý do chọn Jersey

Jersey đáng cân nhắc khi:
- Cả tổ chức hoặc hệ thống đã định chuẩn **JAX-RS resources**; muốn đồng nhất API code giữa vài Java platforms.
- Dự án hiện có providers, filters, exception mappers và resource models của Jakarta REST.
- Có yêu cầu di chuyển/đồng dùng một số endpoint trên Jersey/Jakarta EE runtime.
- Nhóm hiểu Jersey/HK2/Spring integration, và pipeline test/deploy phục vụ được nó.

### 3.2. Những lý do ưu tiên Spring MVC

MVC thường thuận tiện khi:
- Codebase đã sử dụng @RestController, @ControllerAdvice, Spring MVC validation, formatters và message converters.
- Ứng dụng dùng server-side template HTML, view resolution, static resource handling hoặc MVC-specific libraries.
- Công cụ quan sát, security, testing, OpenAPI và logging trong tổ chức đã chuẩn hóa theo Spring MVC.
- Yêu cầu chính chỉ là JSON REST endpoints phổ thông, không có lợi ích rõ khi đổi programming model.

### 3.3. Không suy luận hiệu năng từ tên framework

Không có kết luận tổng quát rằng Jersey luôn nhanh hơn MVC hay ngược lại. Benchmark cần cùng JVM, phiên bản Tomcat, thread count, payload, JSON library, routing complexity, TLS, warmup và deployment. Cần đo **throughput, p95/p99 latency, CPU, GC, memory** trên workload thật. Một endpoint trả “hello” không phản ánh đầy đủ hiệu năng ứng dụng khi chạy database và external HTTP calls.

**Câu hỏi kiến trúc nên đặt:** có lợi ích portability hoặc reuse JAX-RS APIs nào đủ lớn so với chi phí có thêm một web programming model không?

## 4. Spring Boot Jersey auto-configuration

### 4.1. Starter và ResourceConfig

Trong Spring Boot 3.3, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jersey</artifactId>
</dependency>
~~~

Spring Boot có auto-configuration cho Jersey, nhưng vẫn cần **ResourceConfig bean** đăng ký resources:

~~~java
@Component
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
        register(ItemsResource.class);
    }
}
~~~

Đây là **skeleton minh họa**; file đầy đủ ở phần thực hành. Spring Boot tự đăng ký servlet/filter từ ResourceConfig khi starter và điều kiện web runtime phù hợp.

### 4.2. Vì sao explicit register rất quan trọng?

Jersey có giới hạn khi **quét package trong executable JAR và WAR** do nested archive/classloader. Tài liệu Spring Boot 3.3 cảnh báo Jersey **packages(...)** có thể không phát hiện resource trong một package của fully executable JAR hoặc trong **WEB-INF/classes** của executable WAR. Vì vậy:

~~~java
register(GreetingResource.class);
register(ItemResource.class);
register(ItemNotFoundMapper.class);
~~~

là cách được khuyến nghị. Nó làm rõ đường đi của resource/provider và giúp kiểm tra qua code review.

**Đừng cho rằng** Spring @ComponentScan tự bảo đảm Jersey đăng ký hết @Path classes. Spring quản lý bean lifecycle; còn Jersey cần biết resource classes/providers thông qua ResourceConfig. Hai công việc này liên quan nhưng khác nhau.

### 4.3. ResourceConfig và Spring @Component

Khai báo ResourceConfig là **@Component** và các resource là **@Component**. Jersey có Spring integration nên resource có thể inject **Spring @Service/@Repository** qua constructor:

~~~java
@Component
@Path("/hello")
class HelloResource {
    private final GreetingService service;

    public HelloResource(GreetingService service) {
        this.service = service;
    }
}
~~~

Đây là **skeleton**, không phải standalone class, vì GreetingService chưa được định nghĩa ở đây. Khi dùng Spring-managed resources, Spring quyết định singleton/proxy/transactional behavior. Jersey còn có HK2 injector cho providers của nó; đừng tự new một Spring component rồi kỳ vọng @Autowired hoạt động.

### 4.4. Mặc định Jersey là servlet

Spring Boot 3.3 mặc định đăng ký Jersey trong **ServletRegistrationBean** có tên bean **jerseyServletRegistration**, mapped **/* nếu không thay đổi**. Servlet initialization thường lazy; có thể cấu hình **spring.jersey.servlet.load-on-startup** để phát hiện lỗi sớm lúc startup.

~~~yaml
spring:
  jersey:
    type: servlet
    servlet:
      load-on-startup: 1
~~~

Spring Boot cũng hỗ trợ đăng ký Jersey như **filter** bằng **spring.jersey.type=filter** với bean **jerseyFilterRegistration** và điều chỉnh **spring.jersey.filter.order**. Lựa chọn này quan trọng khi chạy Jersey cùng MVC, nhưng không nên đổi sang filter nếu chưa có nhu cầu.

### 4.5. Jersey application path và Servlet context path

Bạn có thể dùng annotation **@ApplicationPath("/api")** trên ResourceConfig, hoặc thuộc tính **spring.jersey.application-path: /api**. Nếu cả hai được khai báo, property có thể override giá trị annotation; tốt nhất chỉ có một nguồn cấu hình rõ ràng.

URL cuối cùng là:

~~~text
Servlet context path + Jersey application path
  + resource class @Path + resource method @Path

Ví dụ:
/shop + /api + /items + /42
  = /shop/api/items/42
~~~

Không đặt /api lặp lại vào mọi @Path khi đã khai báo @ApplicationPath. Nếu dùng **server.servlet.context-path: /shop**, URL tăng prefix /shop; không cần thêm /shop vào ResourceConfig.

## 5. Một Spring Boot Jersey REST API chạy được

Demo gồm:
- **GET /api/hello?name=Lan** → 200 JSON greeting.
- **GET /api/items** → 200 JSON list.
- **POST /api/items** → 201 Created và Location header.
- **GET /api/items/{id}** → 200 JSON item; ID không tồn tại → 404 JSON.
- POST JSON với name rỗng → 400 JSON.
- Resource có **Spring DI**, Jersey **ExceptionMapper**, JSON **JacksonFeature** và test **HTTP server thật**.

Dữ liệu được lưu trong ConcurrentHashMap trong một JVM để dễ học; **không dùng thay database production**.

### 5.1. Tạo project

Yêu cầu:
- Java 17+.
- Maven 3.6+ hoặc Maven wrapper.
- Cổng 8080 rảnh.
- Package **com.example.jerseydemo**.

Cây thư mục:

~~~text
jersey-runtime-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/jerseydemo/
    JerseyRuntimeApplication.java
    JerseyConfiguration.java
    GreetingResource.java
    Item.java
    NewItemRequest.java
    ErrorResponse.java
    ItemNotFoundException.java
    ItemNotFoundMapper.java
    ItemService.java
    ItemResource.java
  src/main/resources/
    application.yml
  src/test/java/com/example/jerseydemo/
    JerseyHttpIntegrationTest.java
~~~

Không dùng spring-boot-starter-web trong project chính: **spring-boot-starter-jersey** là REST alternative, đã mang phần Servlet web runtime tương ứng. Không dùng @RestController để tránh lẫn pipeline.

### 5.2. pom.xml hoàn chỉnh

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
    <artifactId>jersey-runtime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jersey</artifactId>
        </dependency>
        <dependency>
            <groupId>org.glassfish.jersey.media</groupId>
            <artifactId>jersey-media-json-jackson</artifactId>
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

**jersey-media-json-jackson** bảo đảm Jersey có Jackson JSON provider tương ứng cho DTOs. Trong một số starter/version, provider có thể đã được kéo transitively; khai báo explicit giúp bài minh bạch. Spring Boot parent/BOM quản lý dependency versions; không trộn Jersey 2 vào Jersey 3.

### 5.3. Main class

**src/main/java/com/example/jerseydemo/JerseyRuntimeApplication.java**

~~~java
package com.example.jerseydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JerseyRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(JerseyRuntimeApplication.class, args);
    }
}
~~~

### 5.4. ResourceConfig: điểm kết nối Jersey và Boot

**src/main/java/com/example/jerseydemo/JerseyConfiguration.java**

~~~java
package com.example.jerseydemo;

import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.jackson.JacksonFeature;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfiguration extends ResourceConfig {

    public JerseyConfiguration() {
        register(GreetingResource.class);
        register(ItemResource.class);
        register(ItemNotFoundMapper.class);
        register(JacksonFeature.class);

        property("jersey.config.server.response.setStatusOverSendError",
                true);
    }
}
~~~

- **@Component** giúp Spring Boot có ResourceConfig bean.
- **@ApplicationPath("/api")** đặt prefix cho tất cả Jersey resources.
- **register(...)** liệt kê resources và providers để không phụ thuộc package scanning trong executable JAR/WAR.
- **JacksonFeature** dùng Jersey/Jackson JSON provider, không phải Spring MVC HttpMessageConverter.
- **setStatusOverSendError** giúp tương tác với một số hành vi Spring Security method security nếu dự án sau này bật Security; nó không tự thêm Security vào project.
- Không tạo nhiều ResourceConfig beans ngẫu nhiên; khi cần modular configuration, có thể dùng **ResourceConfigCustomizer** theo tài liệu Boot.

### 5.5. GET resource

**src/main/java/com/example/jerseydemo/GreetingResource.java**

~~~java
package com.example.jerseydemo;

import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import org.springframework.stereotype.Component;

@Component
@Path("/hello")
@Produces(MediaType.APPLICATION_JSON)
public class GreetingResource {
    public record Greeting(String message) { }

    @GET
    public Greeting hello(
            @DefaultValue("Java") @QueryParam("name") String name) {
        return new Greeting("Xin chào, " + name);
    }
}
~~~

Resource path **/hello** được ghép sau application path **/api** → URL **/api/hello**. @DefaultValue áp dụng khi query parameter name không có; không có nghĩa blank name luôn được thay bằng Java. @Produces khai báo JSON response media type.

### 5.6. Item.java

**src/main/java/com/example/jerseydemo/Item.java**

~~~java
package com.example.jerseydemo;

public record Item(long id, String name) { }
~~~

### 5.7. NewItemRequest.java

**src/main/java/com/example/jerseydemo/NewItemRequest.java**

~~~java
package com.example.jerseydemo;

public record NewItemRequest(String name) { }
~~~

Java record có sẵn trên Java 17. Jersey Jackson provider chuyển JSON body sang record và ngược lại khi phiên bản Jackson phù hợp.

### 5.8. ErrorResponse.java

**src/main/java/com/example/jerseydemo/ErrorResponse.java**

~~~java
package com.example.jerseydemo;

public record ErrorResponse(String code, String message) { }
~~~

### 5.9. ItemNotFoundException.java

**src/main/java/com/example/jerseydemo/ItemNotFoundException.java**

~~~java
package com.example.jerseydemo;

public class ItemNotFoundException extends RuntimeException {
    public ItemNotFoundException(long id) {
        super("Item " + id + " was not found");
    }
}
~~~

### 5.10. ItemService.java

**src/main/java/com/example/jerseydemo/ItemService.java**

~~~java
package com.example.jerseydemo;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class ItemService {
    private final ConcurrentMap<Long, Item> items =
            new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    public Item create(String name) {
        long id = nextId.incrementAndGet();
        Item item = new Item(id, name);
        items.put(id, item);
        return item;
    }

    public Item find(long id) {
        Item item = items.get(id);
        if (item == null) {
            throw new ItemNotFoundException(id);
        }
        return item;
    }

    public List<Item> list() {
        return items.values().stream()
                .sorted(Comparator.comparingLong(Item::id))
                .toList();
    }
}
~~~

Đây là **Spring @Service**. Jersey resource sẽ được Spring inject service này. ConcurrentHashMap và AtomicLong chỉ giải quyết vấn đề concurrent access tối thiểu; state mất khi restart, không share giữa replicas, không bảo đảm transaction hay persistence. Với dữ liệu thật cần repository, DB, constraints và authorization.

### 5.11. ItemResource.java: JSON GET, POST 201, Location

**src/main/java/com/example/jerseydemo/ItemResource.java**

~~~java
package com.example.jerseydemo;

import java.net.URI;
import java.util.List;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.UriInfo;
import org.springframework.stereotype.Component;

@Component
@Path("/items")
@Produces(MediaType.APPLICATION_JSON)
public class ItemResource {
    private final ItemService service;

    public ItemResource(ItemService service) {
        this.service = service;
    }

    @GET
    public List<Item> list() {
        return service.list();
    }

    @GET
    @Path("/{id}")
    public Item find(@PathParam("id") long id) {
        return service.find(id);
    }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public Response create(
            NewItemRequest request,
            @Context UriInfo uriInfo) {

        if (request == null || request.name() == null
                || request.name().isBlank()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .type(MediaType.APPLICATION_JSON)
                    .entity(new ErrorResponse(
                        "INVALID_NAME", "name must not be blank"))
                    .build();
        }

        Item item = service.create(request.name().trim());
        URI location = uriInfo.getAbsolutePathBuilder()
                .path(Long.toString(item.id()))
                .build();

        return Response.created(location)
                .type(MediaType.APPLICATION_JSON)
                .entity(item)
                .build();
    }
}
~~~

**Giải thích quan trọng:**
1. @Path("/items") sau @ApplicationPath("/api") tạo URL /api/items.
2. @GET list() dùng ItemService.list() trả List<Item>, được JSON provider serialize.
3. @GET @Path("/{id}") nhận path ID qua JAX-RS @PathParam.
4. @POST @Consumes JSON yêu cầu Content-Type application/json; Jersey MessageBodyReader chuyển body thành NewItemRequest.
5. @Context UriInfo cung cấp absolute request URI để sinh Location cho item mới.
6. Response.created(location) trả **HTTP 201 Created** và header **Location**, entity Item là JSON nếu provider hoạt động.
7. Input blank được chặn bằng **400 Bad Request** và ErrorResponse, không lộ stack trace.
8. Class là Spring @Component và constructor-inject ItemService; không tự new service.
9. Đặt validation trong service/validator riêng khi app lớn; ở đây để trong method cho dễ đọc.
10. Production phải thêm size limits, auth, transaction, data persistence và tránh expose raw internal URLs sau reverse proxy.

### 5.12. ExceptionMapper cho 404

**src/main/java/com/example/jerseydemo/ItemNotFoundMapper.java**

~~~java
package com.example.jerseydemo;

import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

@Provider
public class ItemNotFoundMapper
        implements ExceptionMapper<ItemNotFoundException> {

    @Override
    public Response toResponse(ItemNotFoundException ex) {
        return Response.status(Response.Status.NOT_FOUND)
                .type(MediaType.APPLICATION_JSON)
                .entity(new ErrorResponse(
                    "ITEM_NOT_FOUND", ex.getMessage()))
                .build();
    }
}
~~~

**@Provider** là JAX-RS extension annotation. **register(ItemNotFoundMapper.class)** trong ResourceConfig là bước quan trọng để mapper được dùng. Đừng dùng Spring @ControllerAdvice rồi mong nó tự bắt lỗi Jersey resource. Mapper này xử lý đúng type ItemNotFoundException, không thay thế toàn bộ servlet error handling.

### 5.13. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: jersey-runtime-demo
  jersey:
    type: servlet
    servlet:
      load-on-startup: 1

server:
  port: 8080
~~~

Chúng ta đặt application path bằng **@ApplicationPath("/api")**; không khai báo thêm spring.jersey.application-path ở YAML để tránh cấu hình trùng. Load-on-startup=1 giúp Jersey initialize khi startup, tiện phát hiện lỗi provider/registration trước khi nhận request. Mặc định Boot đăng ký Jersey như Servlet; type: servlet chỉ làm rõ lựa chọn.

### 5.14. Build và chạy

Linux/macOS/Git Bash:

~~~bash
./mvnw clean package
java -jar target/jersey-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Windows CMD/PowerShell:

~~~text
mvnw.cmd clean package
java -jar target/jersey-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu không có Maven wrapper, dùng:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Không chạy đồng thời jar và spring-boot:run khi cả hai chiếm port 8080. Ứng dụng REST chỉ có Jersey, không cần @EnableWebMvc.

## 6. Thử API bằng curl và kiểm tra output

### 6.1. GET với query parameter

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

Kỳ vọng **200 OK**, Content-Type application/json, body:

~~~json
{"message":"Xin chào, Lan"}
~~~

### 6.2. GET với DefaultValue

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Body:

~~~json
{"message":"Xin chào, Java"}
~~~

Nếu gửi ?name= rỗng, đừng nhầm với trường hợp không gửi tham số; DefaultValue không bắt buộc thay blank value.

### 6.3. List ban đầu

~~~bash
curl -i http://localhost:8080/api/items
~~~

Nếu ứng dụng vừa khởi động và chưa có POST, JSON body thường là:

~~~json
[]
~~~

### 6.4. POST tạo item

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Sổ tay"}'
~~~

Khi đây là item đầu tiên sau fresh startup, kỳ vọng **201 Created** với Location tương tự:

~~~http
Location: http://localhost:8080/api/items/1
~~~

và body:

~~~json
{"id":1,"name":"Sổ tay"}
~~~

Nếu đã có item, ID có thể là 2, 3...; không kiểm thử bằng cách luôn khẳng định id=1. Host/scheme trong Location đến từ request UriInfo; phía sau reverse proxy cần cấu hình forwarded headers được tin cậy để không lộ internal URL.

### 6.5. GET item

~~~bash
curl -i http://localhost:8080/api/items/1
~~~

Nếu ID 1 tồn tại, trả **200** và JSON. Với ứng dụng thật, frontend nên theo URI trong Location chứ không tự đoán ID.

### 6.6. POST không hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H 'Content-Type: application/json' \
  -d '{"name":"   "}'
~~~

Kỳ vọng **400 Bad Request**:

~~~json
{"code":"INVALID_NAME","message":"name must not be blank"}
~~~

### 6.7. GET không tìm thấy

~~~bash
curl -i http://localhost:8080/api/items/-99
~~~

Kỳ vọng **404 Not Found** và JSON:

~~~json
{"code":"ITEM_NOT_FOUND","message":"Item -99 was not found"}
~~~

Không gửi stack trace hoặc chi tiết filesystem/database lỗi cho client.

### 6.8. Content negotiation

Khi POST request **Content-Type: text/plain** vào method chỉ @Consumes JSON, Jersey có thể trả **415 Unsupported Media Type**. Khi GET có **Accept: application/xml** mà method chỉ @Produces JSON, có thể trả **406 Not Acceptable**. Một method không hỗ trợ verb cụ thể (ví dụ PUT vào /api/items) có thể trả **405 Method Not Allowed**.

**Accept** là kiểu response client chấp nhận; **Content-Type** là kiểu body request được gửi. Cả hai thuộc JAX-RS provider selection, không phải MVC HttpMessageConverter của project demo. Format body lỗi default có thể thay đổi theo Jersey/version; test hợp đồng trạng thái và public error schema do app định nghĩa thay vì so khớp nguyên header server.

## 7. Test Jersey với embedded HTTP server thật

### 7.1. Vì sao không dùng MockMvc làm test chính?

**MockMvc** chạy logic **Spring MVC DispatcherServlet**, không thực hiện routing của Jersey Servlet. Test @WebMvcTest/MockMvc có thể báo 404 cho @Path resource dù ứng dụng Jersey production chạy đúng. Test Jersey đúng hướng nên khởi động Servlet runtime thật, ví dụ **@SpringBootTest(webEnvironment=RANDOM_PORT)**, rồi gửi HTTP bằng Java HttpClient hay TestRestTemplate.

Test real server giúp phát hiện:
- ResourceConfig không đăng ký resource/provider.
- Servlet mapping sai, application path lặp.
- JSON MessageBodyReader/Writer thiếu.
- Phản hồi 201/Location không đúng.
- Servlet filters/security/proxy-related behavior khi có cấu hình tương ứng.

### 7.2. Test class đầy đủ

**src/test/java/com/example/jerseydemo/JerseyHttpIntegrationTest.java**

~~~java
package com.example.jerseydemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class JerseyHttpIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpResponse<String> send(HttpRequest request)
            throws Exception {
        return http.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void helloReturnsJson() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/hello?name=Lan"))
                .header("Accept", "application/json")
                .GET().build();

        HttpResponse<String> response = send(request);
        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("Xin chào, Lan",
                body.path("message").asText());
    }

    @Test
    void postCreatesItemAndGetReadsIt() throws Exception {
        HttpRequest create = HttpRequest.newBuilder(
                uri("/api/items"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"Sổ tay\"}"))
                .build();

        HttpResponse<String> created = send(create);
        assertEquals(201, created.statusCode());

        JsonNode body = mapper.readTree(created.body());
        long id = body.path("id").asLong();
        assertTrue(id > 0);
        assertEquals("Sổ tay", body.path("name").asText());

        String location = created.headers()
                .firstValue("Location").orElseThrow();
        assertTrue(location.endsWith("/api/items/" + id));

        HttpRequest read = HttpRequest.newBuilder(
                URI.create(location)).GET().build();
        HttpResponse<String> found = send(read);

        assertEquals(200, found.statusCode());
        JsonNode item = mapper.readTree(found.body());
        assertEquals(id, item.path("id").asLong());
        assertEquals("Sổ tay", item.path("name").asText());
    }

    @Test
    void blankNameReturns400() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"  \"}"))
                .build();

        HttpResponse<String> response = send(request);
        assertEquals(400, response.statusCode());

        JsonNode error = mapper.readTree(response.body());
        assertEquals("INVALID_NAME",
                error.path("code").asText());
    }

    @Test
    void missingItemUsesJerseyExceptionMapper()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items/-99")).GET().build();

        HttpResponse<String> response = send(request);
        assertEquals(404, response.statusCode());

        JsonNode error = mapper.readTree(response.body());
        assertEquals("ITEM_NOT_FOUND",
                error.path("code").asText());
    }
}
~~~

**Các lưu ý test:**
- @LocalServerPort ở Boot 3.3 thuộc package **org.springframework.boot.test.web.server**.
- Java 17 có sẵn HttpClient; không cần bổ sung library HTTP test khác.
- Test tạo item đọc ID/Location từ response thay vì phụ thuộc thứ tự test.
- Negative ID -99 không thể được AtomicLong tăng từ 1 tạo trong lab.
- Test body bằng Jackson parsing, không assert nguyên Date, Content-Length hoặc header order.
- RANDOM_PORT tạo server thật; test client và HTTP server hoạt động ở các threads khác nhau. Không dựa vào @Transactional của test để tự rollback các thay đổi server-side.
- Project demo không có DB nên test state trong bộ nhớ có thể tồn tại giữa tests; test tránh giả định list luôn rỗng.
- Với external proxy/HTTPS production, còn phải kiểm thử Location scheme/host và TLS/security behavior trên deployment thật.

Chạy test:

~~~bash
./mvnw test
~~~

Sau đó thử runtime executable JAR:

~~~bash
./mvnw package
java -jar target/jersey-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Jersey package scanning có thể khác giữa IDE, Maven và executable JAR. Lợi ích của explicit register là resource list cố định dù deployment classloader khác.

## 8. JSON providers, media types và DTOs

### 8.1. Jersey không dùng Spring MVC HttpMessageConverter

JAX-RS chọn **MessageBodyReader** để parse body và **MessageBodyWriter** để viết response. Jersey JacksonFeature/Jersey JSON dependency là provider implementation. Spring MVC lại có **HttpMessageConverter**, đối tượng khác. Dù ứng dụng dùng Spring Boot ObjectMapper, **không mặc định mọi tùy chỉnh ObjectMapper của MVC áp dụng cho Jersey**.

~~~text
HTTP Content-Type + Accept
          |
          v
Jersey @Consumes / @Produces
          |
          v
MessageBodyReader / MessageBodyWriter
          |
          v
JAX-RS resource method, DTO, Response
~~~

Nếu cần date/time module, enum serialization, schema naming, null policy hoặc polymorphic types, hãy cấu hình Jersey JSON provider theo version thật và viết HTTP contract tests. Không giả định chỉ cần thêm @JsonComponent kiểu MVC là Jersey tự phát hiện tất cả.

### 8.2. 400, 405, 406, 415 thuộc các tầng khác nhau

- **400 Bad Request**: client input không hợp lệ hoặc không parse được theo contract.
- **405 Method Not Allowed**: URL/resource có nhưng không chấp nhận HTTP method.
- **406 Not Acceptable**: Accept không tương thích response media type.
- **415 Unsupported Media Type**: Content-Type request không tương thích @Consumes/reader.
- **404 Not Found**: không có resource/route hoặc domain item không tồn tại.

Không viết global ExceptionMapper<Throwable> trả HTTP 400 cho mọi exception, vì như vậy che mất server bugs thành client error. Map domain exceptions có kiểm soát và giữ server 500 cho unexpected failures, với logs an toàn.

### 8.3. Jakarta Bean Validation

Jersey có thể tích hợp Jakarta Bean Validation, nhưng **phải có implementation và Jersey integration/provider tương thích**, chẳng hạn các module Jersey validation phù hợp. Chỉ gắn @NotBlank lên NewItemRequest không bảo đảm runtime tự gọi validator theo cách bạn kỳ vọng. Project demo dùng kiểm tra name thủ công để không ẩn dependency. Production nên có:
- bean validation/constraint mapping;
- message structure và i18n;
- thống nhất 400 cho field errors;
- payload size limits;
- test JSON invalid, missing fields, Unicode và special characters.

### 8.4. JSON response không bảo đảm API an toàn

Trả JSON có thể lộ dữ liệu nếu không có authentication/authorization. Cần kiểm soát sensitive fields, logging, cache policy, CSRF nếu session cookie, CORS khi browser cross-origin và output sanitation. MediaType.APPLICATION_JSON chỉ là biểu diễn dữ liệu, không là biện pháp bảo mật.

## 9. ExceptionMapper, providers và filters

### 9.1. Thay @ControllerAdvice bằng ExceptionMapper

Jersey **@Provider ExceptionMapper<T>** xử lý exception ném từ JAX-RS resource pipeline. Trong project demo, ItemNotFoundMapper trả 404 JSON. Mỗi mapper cần được đăng ký trong ResourceConfig nếu không có discovery đáng tin. Với MVC, @ControllerAdvice/@ExceptionHandler là cơ chế tương đương về mục đích nhưng khác framework; **không dùng @ControllerAdvice để xử lý Jersey request**.

### 9.2. ContainerRequestFilter

JAX-RS định nghĩa **ContainerRequestFilter** để xử lý request ở tầng Jersey. Có thể dùng để ghi metadata không nhạy cảm hoặc thêm correlation context:

~~~java
@Provider
public class AuditFilter implements ContainerRequestFilter {
    @Override
    public void filter(ContainerRequestContext context)
            throws IOException {
        String method = context.getMethod();
        String path = context.getUriInfo().getPath();
        // Chỉ log metadata đã được cho phép.
    }
}
~~~

**Đây là snippet không độc lập**; khi thêm vào project phải import **jakarta.ws.rs.container.ContainerRequestFilter/ContainerRequestContext**, **jakarta.ws.rs.ext.Provider**, **java.io.IOException**, và đăng ký **register(AuditFilter.class)** trong ResourceConfig. Không ghi cookies, Authorization headers, user secrets hay toàn bộ payload.

### 9.3. ContainerResponseFilter

Một provider có thể thêm response header:

~~~java
@Provider
public class MarkerFilter implements ContainerResponseFilter {
    @Override
    public void filter(ContainerRequestContext request,
                       ContainerResponseContext response)
            throws IOException {
        response.getHeaders().add(
                "X-Demo-Framework", "jersey");
    }
}
~~~

**Đây cũng là snippet**, cần các imports jakarta.ws.rs.container.*, jakarta.ws.rs.ext.Provider và java.io.IOException. Không tự register vào project demo nếu không dùng. Servlet Filter nằm ngoài Jersey và có thể áp dụng cho cả MVC/Jersey; ContainerResponseFilter chỉ thuộc Jersey pipeline.

### 9.4. Thứ tự filter và @PreMatching

JAX-RS có **@PreMatching** và **@Priority** cho providers, khác Spring @Order và Servlet filter order. Một HTTP request có thể đi qua Spring Security Servlet Filter trước Jersey request filters, rồi mới tới JAX-RS resource. Muốn filter nào kiểm tra authentication hoặc CORS, phải chọn đúng tầng và test request thật; không coi @Priority(HIGH) tương đương chạy trước SecurityFilterChain.

## 10. Dependency injection, lifecycle và thread safety

### 10.1. @Component quan trọng

Spring Boot Jersey integration hỗ trợ resource là **Spring @Component**, được inject Spring @Service. ItemResource constructor nhận ItemService là ví dụ đầy đủ. Nhưng Jersey còn có HK2/service locator cho providers không thuộc Spring. Một provider do HK2 tạo không bảo đảm nhận mọi Spring @Autowired như Spring bean nếu chưa được integration đúng.

**Không new thủ công** Jersey resource có Spring dependencies trong ResourceConfig. Nếu dùng register(new Resource()), tự bạn chịu lifecycle/state/injection. Ưu tiên register(Resource.class) và Spring-managed beans.

### 10.2. Singleton resources không giữ request state

Spring @Component thường singleton. Không để biến instance mutable chứa currentUser hoặc currentRequest:

~~~java
@Component
@Path("/danger")
public class UnsafeResource {
    private String currentUser;
}
~~~

Đây là **anti-pattern**; concurrent requests có thể ghi đè. Lấy thông tin user từ security context/request context trong method, dùng local variables hoặc properly scoped beans. Đừng lưu HttpServletRequest vào singleton field để dùng sau request.

### 10.3. Spring @Transactional và proxy

Nếu Spring service được inject qua Spring proxy, @Transactional có thể hoạt động trên service method. Nhưng gọi method nội bộ/self-invocation của cùng bean có thể bỏ qua proxy theo quy tắc Spring AOP. Không giả định mọi class do Jersey/HK2 tạo đều được Spring AOP quản lý; kiểm chứng transaction, caching, method security thật trên ứng dụng.

### 10.4. Context objects JAX-RS

**@Context UriInfo** cung cấp URI và path info, đã dùng để tạo Location header. Các loại khác như HttpHeaders, SecurityContext và Servlet request cũng có thể được inject khi runtime hỗ trợ. Đó là JAX-RS context injection, không phải Spring @RequestParam/@PathVariable, và không tự tồn tại trong một chương trình Java thuần hay reactive WebFlux.

## 11. Jersey cùng Spring MVC: quản lý URL ownership

### 11.1. Jersey servlet mặc định /* có thể chiếm request

Nếu dùng spring-boot-starter-jersey với servlet mặc định **/* đồng thời có MVC DispatcherServlet, Jersey có thể nhận các paths mà bạn tưởng Spring MVC sẽ xử lý. Kết quả thường là **MVC @RestController bất ngờ 404** hoặc static assets không tới handler mong đợi.

Một cách dễ kiểm soát là **tách namespace**:
- Jersey: **/jaxrs/**.
- MVC: **/ui/** hoặc **/mvc-api/**.
- Management: private port/path riêng.
- Static resources: servlet/static mapping được thiết kế rõ.

Đặt **@ApplicationPath("/jaxrs")** hoặc spring.jersey.application-path tùy nhu cầu. **Servlet mapping được quyết định trước framework method mapping**; hai framework không tự chia route dựa vào ai có annotation phù hợp.

### 11.2. Filter mode để phối hợp fallback

Nếu cần Jersey chạy cùng web framework khác theo mô hình forward-on-404, Spring Boot hướng dẫn:

1. Đặt **spring.jersey.type: filter**.
2. Trong ResourceConfig, đặt **ServletProperties.FILTER_FORWARD_ON_404: true**.
3. Có một Servlet khác (ví dụ MVC DispatcherServlet) để nhận request mà Jersey không xử lý.
4. Kiểm tra filter order, forward dispatch, security và error handling.

Ví dụ config **chỉ dành cho biến thể coexistence**, không phải file project chính:

~~~yaml
spring:
  jersey:
    type: filter
    filter:
      order: 0
~~~

Cấu hình ResourceConfig tương ứng cần import **org.glassfish.jersey.servlet.ServletProperties** và khai báo:

~~~java
property(ServletProperties.FILTER_FORWARD_ON_404, true);
~~~

Trong app không có servlet xử lý request còn lại, tài liệu Boot gợi ý có thể bật **server.servlet.register-default-servlet: true**, nhưng phải kiểm tra nó có làm static files bị expose sai không. Khi có ExceptionMapper riêng xử lý mọi 404, forwarding behavior có thể khác; test routes thật.

### 11.3. Không trộn hai JSON/error pipelines vô thức

Nếu cùng app có MVC + Jersey:
- MVC dùng HttpMessageConverter, Jersey dùng MessageBodyReader/Writer.
- MVC @ControllerAdvice không bắt Jersey exceptions.
- CORS configured bằng WebMvcConfigurer không tự áp dụng cho Jersey servlet.
- MVC argument converters không tự cho JAX-RS @QueryParam.
- MVC route metrics/tags không tự giống Jersey route metrics.
- OpenAPI adapter chỉ scan MVC controllers có thể bỏ Jersey resources.

Đặt public API contract chung (status, JSON schema, error codes) rồi kiểm thử cả hai pipelines. Nếu không có yêu cầu migration/module đặc thù, một web framework thường đơn giản hơn.

## 12. Spring Security và CORS/CSRF với Jersey

### 12.1. Servlet Security Filter vẫn có thể bảo vệ Jersey

Trong Servlet application, **Spring SecurityFilterChain** nằm ở tầng Servlet filters, nên có thể bảo vệ Jersey URLs khi request matcher và filter registration được cấu hình đúng. **@Component @Path** không tự biến resource thành authorized endpoint; vẫn cần authentication, authorization theo path/method/resource.

Ví dụ **snippet tham khảo** nếu ứng dụng đã thêm spring-boot-starter-security và authentication provider:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Snippet này chưa gồm imports, user store hoặc chính sách CSRF; không copy nó như một project Spring Security hoàn chỉnh. Khi thêm security vào project chính, hãy kiểm tra 401/403 bằng HTTP tests, đặc biệt với Jersey servlet/filter registration.

### 12.2. Method-level security cần chú ý setStatusOverSendError

Tài liệu Spring Boot Jersey how-to khuyên đặt Jersey property:

~~~java
property("jersey.config.server.response.setStatusOverSendError",
        true);
~~~

Khi dùng Spring Security method security, việc Jersey dùng **setStatus** thay **sendError** giúp tránh commit response quá sớm, để security có cơ hội xử lý authentication/authorization failure. Demo đã đặt property đó trong ResourceConfig, nhưng **không có spring-boot-starter-security** nên nó không tự bật security.

Nếu dùng @EnableMethodSecurity và @PreAuthorize trên Spring-managed Jersey resources/service, đảm bảo proxy/advice hoạt động thật. Không cho rằng một annotation trong source đủ bảo vệ endpoint nếu resource bị Jersey tạo ngoài Spring proxy.

### 12.3. CORS không thay authentication

Một request CORS hợp lệ về Origin vẫn phải đi qua auth. Preflight OPTIONS thường không mang session cookie, nên nếu có CORS phải xử lý OPTIONS trước security authentication phù hợp. **Access-Control-Allow-Origin: *** không hợp lệ cho credentialed requests mang cookie. Đừng phản chiếu mọi Origin để chữa lỗi browser. Với Jersey, CORS có thể nằm ở servlet filter, gateway hoặc provider/filter phù hợp; Spring MVC CorsRegistry không tự áp dụng cho Jersey routes.

### 12.4. CSRF khi dùng cookie sessions

Nếu Jersey API được browser gọi với session cookies, unsafe POST/PUT/PATCH/DELETE có thể bị CSRF như MVC. Không disable CSRF toàn cục chỉ vì Jersey POST nhận 403. Chọn synchronizer token hoặc cơ chế tương đương cho session-based browser flows; nếu API chỉ bearer token stateless, đánh giá threat model riêng. Spring Security là tầng bảo vệ, Jersey @POST không tự bảo vệ khỏi CSRF.

## 13. Executable JAR, WAR và reverse proxy

### 13.1. Executable JAR

Spring Boot executable JAR có nested dependencies. Jersey package scanning không bảo đảm tìm resource trong mọi packaged layout. Vì vậy **register resource classes tường minh** là một điểm QA quan trọng, kể cả khi app chạy trong IDE. Test cả **mvn spring-boot:run** và **java -jar** để phát hiện khác biệt classloader/servlet registration.

### 13.2. WAR và Jakarta Servlet

Nếu đóng gói WAR:
- Chuyển packaging phù hợp và quản lý Servlet container dependency/scope.
- Nếu deploy vào external servlet container, có thể cần **SpringBootServletInitializer** trong main application.
- Container cần hỗ trợ **Jakarta Servlet**, không dùng Tomcat 9/javax.servlet với Boot 3.
- Class có thể nằm dưới **WEB-INF/classes**, Jersey packages scanning vẫn có giới hạn.
- Kiểm tra final URL = deployment context + Jersey path + resource path.

Project runnable dùng executable JAR, không giả vờ rằng cấu hình WAR được thử sẵn.

### 13.3. Reverse proxy và Location

HTTP 201 Location được dựng từ UriInfo request. Khi Nginx/ingress chuyển external HTTPS sang internal HTTP, URI có thể sai scheme/host nếu forwarded headers không được xử lý đúng. Chỉ tin **Forwarded / X-Forwarded-Proto / X-Forwarded-Host** từ proxy đáng tin cậy; client ngoài không được tự giả header để sửa Location hoặc redirect. Có tests qua public URL staging.

### 13.4. Blocking behavior

Jersey REST trên embedded Servlet container thường dùng request threads. Một method gọi database hoặc network blocking sẽ giữ thread. JAX-RS có API async/SSE tùy runtime, nhưng không có nghĩa mọi Jersey resource mặc định non-blocking hoặc tương đương WebFlux. Phân tích thread pool, connection pool, timeouts, streaming, graceful shutdown và backpressure theo thực tế.

## 14. Quan sát và tài liệu API

### 14.1. Actuator/metrics

Spring Boot Actuator có thể cung cấp health, metrics, tracing cho Servlet stack dù framework xử lý route là Jersey. Có thể thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Đây là **phần mở rộng**, không nằm trong pom.xml demo. Các tag HTTP server như URI template có thể khác giữa Jersey và MVC vì HandlerMapping khác nhau. Không mặc định Jersey tự gắn tất cả MVC observation conventions. Đo metrics/traces trên runtime thật, bảo vệ Actuator endpoints bằng network/auth rules.

### 14.2. OpenAPI adapter

OpenAPI là contract độc lập framework, nhưng công cụ scan endpoints lại có adapter riêng. Một starter thiết kế để scan Spring @RestController/@RequestMapping **không mặc nhiên quét Jersey @Path/@GET**. Với Jersey cần chọn integration JAX-RS/Jakarta thích hợp và test generated docs có đủ paths, request/response schemas, error codes, auth schemes và versions.

### 14.3. Không log secret trong Jersey filters

Request/response filters và tracing instrumentation chỉ nên ghi method, route template, status, request ID đã được kiểm soát. Tránh log Authorization, cookies, bearer tokens, payload nhạy cảm hoặc user identity theo cách không cần thiết. CORS/log filters không phải phương án giấu lỗi bảo mật.

## 15. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| **404 toàn bộ Jersey routes** | ResourceConfig chưa là bean, @ApplicationPath sai, register thiếu | Kiểm tra @Component, starter, ResourceConfig register và URL. |
| **IDE hoạt động, packaged JAR 404** | packages(...) scanning thiếu class trong archive | Explicit register(Resource.class). |
| **/api/api/items** | Nhân đôi application path | Bỏ prefix trùng ở @Path/config. |
| **MVC endpoints mất sau thêm Jersey** | Jersey servlet /* chiếm route | Tách paths, kiểm tra servlet mapping, cân nhắc filter forwarding. |
| **POST JSON trả 415** | Content-Type/@Consumes/JSON provider mismatch | Kiểm tra Jersey JSON provider, Content-Type. |
| **GET trả 406** | Accept không khớp @Produces | Chỉnh Accept hoặc supported representations. |
| **500 khi serialize DTO** | JacksonFeature/provider/schema lỗi | Đăng ký provider và viết JSON contract test. |
| **Service null trong resource** | Resource không phải Spring bean hoặc tự new | @Component resource, constructor injection, register class. |
| **javax.ws.rs.Path không hoạt động** | Namespace/version Jersey cũ | Dùng jakarta.ws.rs.* và kiểm tra dependency tree. |
| **@ControllerAdvice không bắt lỗi** | Jersey không dùng MVC exception resolver | Dùng @Provider ExceptionMapper. |
| **CORS MVC config vô hiệu** | Jersey servlet không dùng WebMvcConfigurer CORS pipeline | Dùng servlet/gateway/Jersey CORS filter thích hợp. |
| **Spring Security trả 401/403 bất thường** | Filter matchers, session/CSRF, method proxy hoặc preflight | HTTP integration tests và ResourceConfig property. |
| **Test MockMvc không thấy @Path route** | MockMvc chạy MVC dispatcher | Dùng @SpringBootTest(RANDOM_PORT) + HTTP client. |
| **Location header sai host/scheme** | Proxy/forwarded headers | Cấu hình trusted proxy, test public URL. |
| **Resource works only with un-packaged app** | Classloader/servlet configuration | Explicit registration và packaged smoke test. |
| **Static assets/Actuator 404** | Servlet mapping chồng chéo | Phân vùng namespace, kiểm tra Servlet registrations. |
| **Metrics không như MVC** | Observability conventions khác | Kiểm tra instrumentation/URI tags thực tế. |
| **Filter/ExceptionMapper không chạy** | Provider không register hoặc lifecycle sai | Register từng provider và test HTTP. |

### 15.1. Quy trình debug có thứ tự

1. Kiểm tra dependency **spring-boot-starter-jersey**, Java/Jakarta API versions.
2. Kiểm tra một **ResourceConfig bean** đang được Spring tạo.
3. Kiểm tra resource @Component và register class tương ứng.
4. Kiểm tra context path + application path + class/method @Path.
5. Kiểm tra Jersey servlet hoặc filter registration và xung đột MVC.
6. Kiểm tra HTTP verb, Content-Type, Accept, @Consumes/@Produces.
7. Kiểm tra JSON provider và DTO serialization/deserialization.
8. Kiểm tra exception mappers, providers và filters.
9. Kiểm tra Spring Security, CORS, CSRF, authentication trước resource.
10. Build JAR và test trên deployment giống production.

Đừng sửa lỗi route Jersey bằng cách thay ngẫu nhiên spring.mvc.pathmatch hoặc @EnableWebMvc: đó là những cấu hình thuộc MVC, không giải quyết nguyên nhân Jersey servlet mapping.

## 16. Bài tập

### Bài 1: Migrate từ @RestController

Chuyển một GET Spring MVC /customers/{id} dùng @PathVariable thành resource JAX-RS với @Path, @GET và @PathParam. Giữ nguyên URL và JSON contract. Chuyển phần lỗi @ControllerAdvice sang ExceptionMapper, test 200/404 qua RANDOM_PORT.

### Bài 2: So sánh scan và register

Trong bản sao lab, thử đổi register(ItemResource.class) thành packages("com.example.jerseydemo"). Chạy IDE, Maven rồi executable JAR, so route. Sau bài thử, phục hồi explicit register. Giải thích vì sao scanning trong nested JAR có thể thiếu resource.

### Bài 3: Kiểm tra 201

POST tạo item, đọc response Location, dùng chính URL đó để GET item. Không hardcode ID=1. Kiểm tra Location khi thêm Servlet context-path hoặc chạy qua reverse proxy.

### Bài 4: Content negotiation

Thử GET với Accept=application/xml và POST Content-Type=text/plain, quan sát 406/415. Phân biệt @Produces và @Consumes. Viết test chỉ dựa vào HTTP status nếu body lỗi mặc định không thuộc contract của ứng dụng.

### Bài 5: Bảo mật

Thêm Spring Security, chặn POST nếu chưa authenticated hoặc không có quyền EDITOR. Nếu dùng cookie session, kiểm tra CSRF. Đừng dùng CORS làm authorization. Kiểm tra @PreAuthorize trên Spring-managed service qua HTTP thật.

### Bài 6: Coexistence với MVC

Thêm một Spring MVC @Controller phục vụ /ui/hello trong bản lab thử nghiệm. Xác định cách để Jersey chỉ xử lý /api/*, MVC xử lý /ui/*. Nếu muốn Jersey fallback qua filter, bật type=filter và FILTER_FORWARD_ON_404 rồi test cả hai. Chỉ dùng cách phù hợp với kiến trúc thật.

## 17. Checklist trước triển khai

- [ ] Có lý do chọn JAX-RS/Jersey rõ ràng, team hiểu tradeoffs với Spring MVC.
- [ ] Dùng Jersey 3/Jakarta namespace tương thích Boot 3; không trộn javax.ws.rs.*.
- [ ] ResourceConfig được Spring quản lý, resource/provider register tường minh.
- [ ] @Component và Spring service DI hoạt động, không dùng manual new gây mất proxy.
- [ ] @ApplicationPath/Servlet context-path không trùng hoặc cộng hai lần.
- [ ] Jersey servlet/filter mappings không chiếm MVC/static/management routes ngoài dự kiến.
- [ ] JSON MessageBodyReader/Writer, @Consumes, @Produces và DTO records có tests.
- [ ] HTTP 200, 201/Location, 400, 404, 405, 406, 415 được kiểm chứng.
- [ ] ExceptionMapper và providers register, không dựa vào @ControllerAdvice của MVC.
- [ ] Bean lifecycles/scopes, @Transactional, concurrency và request state được xem xét.
- [ ] Authentication, authorization, CORS, CSRF và cookie policies đúng với Servlet stack.
- [ ] Test @SpringBootTest RANDOM_PORT qua HTTP thật, không chỉ MockMvc.
- [ ] Chạy lại tests trên packaged JAR/WAR và external container nếu sử dụng.
- [ ] Proxy trusted forwarded headers, public Location, HTTPS và context prefix đúng.
- [ ] Actuator và tracing/metrics được kiểm tra, không lộ management endpoints.
- [ ] OpenAPI tooling hỗ trợ JAX-RS, generated API docs trùng contract.
- [ ] Không ghi secret vào logs hoặc trả stack traces ra API response.
- [ ] Có thread/resource limits, timeouts, performance và load tests phù hợp.

## 18. Câu hỏi tự kiểm tra

**1. JAX-RS và Jersey có phải là một không?** Không. Jakarta REST/JAX-RS là đặc tả; Jersey là runtime implementation.

**2. Thêm starter Jersey và viết class @Path đã đủ chưa?** Cần ResourceConfig đăng ký resource; nên dùng @Component cho Spring-managed endpoints.

**3. Vì sao dùng register(Resource.class) thay packages(...)?** Jersey package scanning có giới hạn khi nested archives/executable WAR; explicit register tin cậy hơn.

**4. Jersey mặc định là servlet hay filter?** Theo Boot 3.3, mặc định servlet mapping /*; đổi sang filter bằng spring.jersey.type.

**5. Có thể dùng @ControllerAdvice để bắt ItemNotFoundException trong Jersey không?** Không mặc định; dùng ExceptionMapper đăng ký trong ResourceConfig.

**6. @GetMapping và @GET dùng chung DispatcherServlet không?** Không. MVC dùng DispatcherServlet, Jersey có servlet/filter và router riêng.

**7. Test MockMvc đủ chứng minh Jersey servlet chạy đúng chưa?** Chưa; dùng @SpringBootTest(RANDOM_PORT) và HTTP client thật.

**8. Khi POST tạo resource, JAX-RS có API nào hỗ trợ status 201/Location?** jakarta.ws.rs.core.Response.created(location).

**9. Chỉ cần spring-boot-starter-jersey có phải vẫn bắt buộc thêm spring-boot-starter-web?** Không. Jersey starter là lựa chọn thay Spring MVC web starter khi chỉ dùng Jersey.

**10. Vì sao static resource hay MVC endpoint 404 sau khi thêm Jersey?** Kiểm tra Jersey servlet /* và sự chồng chéo Servlet mappings, thay vì chỉ kiểm tra controller annotations.

## 19. Tài liệu chính thức

1. [Spring Boot 3.3 — Servlet Web Applications, JAX-RS and Jersey](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): ResourceConfig, @Component, explicit register, servlet/filter mapping và executable archive scanning.
2. [Spring Boot 3.3 — Jersey How-to](https://docs.spring.io/spring-boot/3.3/how-to/jersey.html): Spring Security setStatusOverSendError và coexistence với MVC bằng filter-forward.
3. [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): spring.jersey.application-path, type, filter order, load-on-startup.
4. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest(RANDOM_PORT), embedded server, testing beyond MockMvc.
5. [Jakarta RESTful Web Services Specification](https://jakarta.ee/specifications/restful-ws/): @Path, @GET, @POST, Response, providers, filters, standard behavior.
6. [Eclipse Jersey Documentation](https://eclipse-ee4j.github.io/jersey.github.io/documentation/latest/): Jersey server runtime, resource methods, JSON, HK2 và Spring integration.
7. [Spring Security Servlet Reference](https://docs.spring.io/spring-security/reference/servlet/index.html): security filter chain, authentication/authorization.
8. [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): Jackson trong Spring Boot và cơ sở so sánh với Jersey provider.

**Kết luận:** Jersey/Jakarta REST là một **lựa chọn thay Spring MVC cho REST HTTP endpoints** khi đội ngũ cần JAX-RS programming model. Spring Boot cung cấp starter và servlet integration nhưng bạn phải chủ động đăng ký **ResourceConfig**, **@Component JAX-RS resources** và providers; tránh package scanning trong executable archive. Để có API chạy đúng, hãy kiểm thử HTTP thật, phân biệt MVC/Jersey pipelines, quản lý rõ URL ownership và filters, đồng thời bảo vệ security, JSON contract, packaging và observability trước khi triển khai.