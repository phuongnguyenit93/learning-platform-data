# Cấu hình ResourceConfig, Jersey servlet hoặc filter và đường dẫn ứng dụng trong Spring Boot

## 1. Mục tiêu của bài học

Khi xây dựng API trên Spring Boot, không phải mọi ứng dụng đều dùng Spring MVC `@RestController`. Một dự án có thể chọn **Jersey**, implementation của **Jakarta RESTful Web Services (JAX-RS/Jakarta REST)**, để viết tài nguyên bằng `@Path`, `@GET`, `@POST`, `@Produces` và `@Consumes`. Spring Boot hỗ trợ tích hợp Jersey trên **Servlet web runtime**, thường dùng Tomcat.

Bốn câu hỏi quyết định cấu hình chính xác:

1. **`ResourceConfig` đăng ký tài nguyên và provider nào?**
2. **Jersey được đặt vào Servlet container ở vai trò `Servlet` hay `Filter`?**
3. **Base URI của Jersey là đường dẫn nào?** Phân biệt `@ApplicationPath`, `spring.jersey.application-path`, context path và `@Path`.
4. **Jersey có chạy cùng Spring MVC/DispatcherServlet không?** Nếu có, cần tránh chiếm mọi URL hoặc cấu hình filter chuyển tiếp khi Jersey không xử lý request.

Bài này dùng Spring Boot **3.x**, **Java 17+**, Jersey sử dụng namespace **`jakarta.ws.rs.*`**. Ví dụ chính chạy độc lập bằng Gradle, sau đó có biến thể Spring MVC + Jersey filter. Các thuộc tính và tên bean được đối chiếu với tài liệu Spring Boot 3.3.

### Ví dụ vấn đề thường gặp

Developer viết:

~~~java
@Path("/hello")
public class HelloResource {
    @GET
    public String hello() {
        return "hello";
    }
}
~~~

nhưng `GET http://localhost:8080/hello` trả 404. Có thể code không sai: resource chưa được `ResourceConfig.register`, Jersey đang ở `/api/*`, toàn ứng dụng có `server.servlet.context-path=/shop`, hoặc request bị `DispatcherServlet`/reverse proxy đưa sai đường.

**Bài học trọng tâm:** cần suy ra URL từ **tất cả các lớp path**, không chỉ nhìn `@Path` trên resource.

## 2. Jersey, Spring MVC và Servlet container khác vai trò

~~~text
HTTP client
    |
    v
Embedded Tomcat / Servlet container
    |
    +--> Servlet mapping: Jersey ServletContainer
    |       |
    |       v
    |    Jersey ResourceConfig -> JAX-RS @Path/@GET/@POST
    |
    +--> Servlet mapping: Spring DispatcherServlet
            |
            v
         @RestController/@GetMapping
~~~

Trong chế độ **Jersey servlet**, Servlet container chọn servlet theo **Servlet URL mapping**. Nếu Jersey mặc định map `/*`, nó có thể nhận gần như mọi request, gây xung đột với DispatcherServlet và static resources. Một servlet khác map `/` không tự được chạy sau khi Jersey trả 404.

Trong chế độ **Jersey filter**, request đi qua Filter chain trước khi tới servlet được chọn. Jersey có thể xử lý request JAX-RS, hoặc (khi được cấu hình) **chuyển tiếp request không phù hợp** để servlet khác, ví dụ Spring MVC DispatcherServlet, xử lý.

| Thành phần | Công nghệ | Trách nhiệm |
| --- | --- | --- |
| `Tomcat` / Servlet container | Jakarta Servlet | Mở HTTP port, chọn servlet mapping, gọi filters, quản lý request/response |
| `ResourceConfig` | Jersey | Khai báo resources, providers, features, Jersey-specific properties |
| `ServletContainer` | Jersey | Adapter triển khai Jersey như một `Servlet` **hoặc** `Filter` |
| `@Path` và `@GET` | JAX-RS | Xác định resource path và HTTP method bên trong Jersey |
| `DispatcherServlet` | Spring MVC | Dispatch các `@Controller` / `@RestController` |
| `ServletRegistrationBean` | Spring Boot | Đăng ký servlet + URL pattern + load-on-startup |
| `FilterRegistrationBean` | Spring Boot | Đăng ký filter + URL pattern + order |
| `server.servlet.context-path` | Spring Boot | Prefix context path chung cho các servlet trên ứng dụng |
| `spring.jersey.application-path` | Spring Boot/Jersey | Base path phục vụ Jersey; **ưu tiên hơn `@ApplicationPath`** |

**Không đánh đồng `ResourceConfig` với `WebMvcConfigurer`.** Cấu hình một resource Jersey bằng `@Path` không làm nó thành một controller Spring MVC; một `@GetMapping` không được `ResourceConfig.register` như JAX-RS endpoint.

## 3. Tạo ứng dụng Jersey trên Spring Boot 3.x

Dependency cơ bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
}
~~~

`spring-boot-starter-jersey` là điểm bắt đầu tích hợp Jersey do Spring Boot cung cấp. Trong Boot 3.x, annotation JAX-RS nằm ở `jakarta.ws.rs`, không phải `javax.ws.rs` của hệ Java EE/Jersey 2 cũ.

| Spring Boot hiện đại | Vai trò |
| --- | --- |
| `org.glassfish.jersey.server.ResourceConfig` | Khai báo app Jersey |
| `org.glassfish.jersey.servlet.ServletContainer` | Servlet/filter adapter |
| `jakarta.ws.rs.Path` | Đường dẫn resource |
| `jakarta.ws.rs.GET`, `POST`, `PUT`, `DELETE` | HTTP method |
| `jakarta.ws.rs.Produces`, `Consumes` | Media type |
| `jakarta.ws.rs.PathParam`, `QueryParam` | URI variables/parameters |
| `jakarta.ws.rs.core.Response` | Status, headers, entity JAX-RS |
| `jakarta.ws.rs.ApplicationPath` | Base path cho JAX-RS app |
| `org.springframework.stereotype.Component` | Đăng ký resource/config vào Spring context |

Không nên trộn artifacts Jersey 2/`javax.ws.rs` với Spring Boot 3/`jakarta.*`. Nếu code chuyển từ Boot 2, kiểm tra imports, dependencies và các JAX-RS providers tương thích Jakarta.

### ResourceConfig cần là một Spring bean

Mẫu điển hình Spring Boot:

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

Spring Boot tìm bean kiểu `ResourceConfig` và tự cấu hình Jersey. Một cách khác là khai báo một bean `@Bean ResourceConfig` trong `@Configuration`, nhưng **chỉ dùng một cấu hình Jersey rõ ràng**, tránh đăng ký nhiều `ResourceConfig` cạnh tranh.

Đăng ký resource bằng `register(SomeResource.class)` giúp Jersey biết rõ tài nguyên phải xử lý. Tài liệu Spring Boot khuyến nghị **đăng ký từng resource rõ ràng** vì package scanning của Jersey gặp giới hạn trong executable JAR và một số executable WAR, đặc biệt classpath dưới `BOOT-INF/classes` hoặc `WEB-INF/classes`. Đừng tin rằng `packages("com.example.api")` luôn hoạt động giống IDE khi đã đóng gói.

### Resource có thể đồng thời là Spring @Component

~~~java
@Component
@Path("/hello")
public class HelloResource {
    private final GreetingService greetingService;

    public HelloResource(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return greetingService.hello();
    }
}
~~~

Với Jersey-Spring integration của starter, Spring quản lý resource được khai báo `@Component` để hỗ trợ dependency injection. Các service constructor-injected đi qua Spring container như những Spring beans khác.

**Không lẫn hai cơ chế tạo đối tượng:** một Jersey resource do Jersey tự dựng không chắc được Spring inject mọi dependency nếu không có integration đúng. Theo mẫu Spring Boot, `@Component` trên resource + `register(ResourceClass.class)` là cách minh bạch. Hãy test injection trong executable JAR thật.

## 4. URL hoàn chỉnh được ghép từ những phần nào?

Với ứng dụng Servlet, một URL ngoài client thường có cấu trúc:

~~~text
http://host:port
  + server.servlet.context-path
  + Jersey application path (servlet/filter URL mapping)
  + JAX-RS resource @Path
  + JAX-RS method @Path (nếu có)
  + ?query-parameters

Ví dụ:
  http://localhost:8080
  + /shop
  + /api
  + /greetings
  + /Linh
  = http://localhost:8080/shop/api/greetings/Linh
~~~

Hãy tách rõ các lớp:

1. **`server.port=8080`**: port network nơi embedded server lắng nghe.
2. **`server.servlet.context-path=/shop`**: servlet context path, nằm trước URL mappings của servlet thuộc context đó.
3. **`@ApplicationPath("/api")`** trên ResourceConfig: base path Jersey.
4. **`@Path("/greetings")`** trên JAX-RS class: resource path tương đối với base.
5. **`@Path("/{name}")`** trên method: path segment bổ sung.
6. Reverse proxy có thể publish URL bên ngoài với prefix khác; việc rewrite path ở proxy **không tự chỉnh** servlet/Jersey mapping của ứng dụng.

`spring.mvc.servlet.path` là cấu hình đường dẫn của **Spring MVC DispatcherServlet**, không phải base path dành cho Jersey. Nếu cần đặt Jersey sang `/rest`, dùng `@ApplicationPath` hoặc `spring.jersey.application-path`, không chỉ đổi `spring.mvc.servlet.path`.

### Ví dụ bảng URL

Giả sử resource `@Path("/greetings")` và method `@GET`:

| server.servlet.context-path | @ApplicationPath | spring.jersey.application-path | URL dự kiến |
| --- | --- | --- | --- |
| không đặt | không đặt | không đặt | `/greetings` (Jersey servlet mặc định `/*`) |
| không đặt | `/api` | không đặt | `/api/greetings` |
| `/shop` | `/api` | không đặt | `/shop/api/greetings` |
| `/shop` | `/api` | `/rest` | `/shop/rest/greetings` |
| `/shop` | `/jaxrs` | `/v2/api` | `/shop/v2/api/greetings` |

**Thứ tự ưu tiên:** nếu cấu hình `spring.jersey.application-path`, Spring Boot dùng thuộc tính đó **thay cho** giá trị của `@ApplicationPath`. Không cộng hai prefix này lại. Giả sử `@ApplicationPath("/api")` và `spring.jersey.application-path=/rest` thì final path dùng **`/rest`**, không phải `/api/rest`.

Khuyến nghị: dành **một base path riêng** như `/rest` hoặc `/jaxrs` khi Jersey chạy cùng Spring MVC để tránh tranh chấp các URL dùng chung.

## 5. Dự án A runnable: Jersey servlet độc lập + ResourceConfig + @ApplicationPath

Dự án A chỉ dùng Jersey + embedded Servlet container. API có 3 operations: GET lời chào, GET theo tên và POST echo. Dùng text/plain để tập trung vào mapping; JSON serialization là chủ đề cấu hình provider khác.

### 5.1. Cấu trúc

~~~text
jersey-servlet-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/jersey/
    │   │   ├── JerseyApplication.java
    │   │   ├── JerseyConfig.java
    │   │   ├── GreetingResource.java
    │   │   └── GreetingService.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/jersey/JerseyServletTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jersey-servlet-lab'
~~~

`build.gradle` (Java 17, Spring Boot 3.3.13 làm ví dụ):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/shop

# Jersey is a servlet by default. Make the lab choice explicit.
spring.jersey.type=servlet

# Eagerly initialize the Jersey servlet in this demonstration.
spring.jersey.servlet.load-on-startup=1

# Application base path is taken from @ApplicationPath("/api")
# on JerseyConfig in this first run.
~~~

Chỉ khi muốn **ghi đè** `@ApplicationPath("/api")`, thêm property `spring.jersey.application-path=/rest`; chưa thêm property này vào lab lúc đầu để thấy rõ annotation có hiệu lực.

### 5.2. Main class

`src/main/java/demo/jersey/JerseyApplication.java`:

~~~java
package demo.jersey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JerseyApplication {
    public static void main(String[] args) {
        SpringApplication.run(JerseyApplication.class, args);
    }
}
~~~

### 5.3. ResourceConfig bean

`src/main/java/demo/jersey/JerseyConfig.java`:

~~~java
package demo.jersey;

import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
    }
}
~~~

`@ApplicationPath("/api")` có nghĩa resource root `/api` *bên trong servlet context*. `register(GreetingResource.class)` là bước đăng ký JAX-RS resource; nó không đổi path và không tự thêm controller Spring MVC.

### 5.4. Spring service được inject vào JAX-RS resource

`src/main/java/demo/jersey/GreetingService.java`:

~~~java
package demo.jersey;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String defaultGreeting() {
        return "Hello from Jersey";
    }

    public String greetingFor(String name) {
        return "Hello, " + name;
    }
}
~~~

`src/main/java/demo/jersey/GreetingResource.java`:

~~~java
package demo.jersey;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.springframework.stereotype.Component;

@Component
@Path("/greetings")
public class GreetingResource {
    private final GreetingService service;

    public GreetingResource(GreetingService service) {
        this.service = service;
    }

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return service.defaultGreeting();
    }

    @GET
    @Path("/{name}")
    @Produces(MediaType.TEXT_PLAIN)
    public String helloName(@PathParam("name") String name) {
        return service.greetingFor(name);
    }

    @POST
    @Consumes(MediaType.TEXT_PLAIN)
    @Produces(MediaType.TEXT_PLAIN)
    public Response echo(String body) {
        return Response.ok("Echo: " + body).build();
    }
}
~~~

Chú ý:

- `@Path` trên class quy định `/greetings`; `@Path("/{name}")` trên method bổ sung `/Linh`.
- `@GET`, `@POST` là các annotation JAX-RS, **không** phải `@GetMapping` hoặc `@PostMapping` của Spring MVC.
- `@Produces(TEXT_PLAIN)` kiểm soát response representation/content negotiation.
- `@Consumes(TEXT_PLAIN)` nói POST chỉ chấp nhận body kiểu plain text phù hợp.
- `@PathParam("name")` đọc path variable; không phải `@PathVariable` của Spring MVC.
- `Response.ok(...).build()` tạo JAX-RS response 200. Ví dụ echo **không lưu dữ liệu thật**, vì vậy không trả 201 Created.
- Constructor nhận `GreetingService` chứng minh Jersey resource là Spring-managed component, khác một POJO Jersey thuần không có Spring integration.

### 5.5. Chạy dự án

Nếu dự án đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper, tạo wrapper bằng Gradle tương thích hoặc dùng `gradle bootRun` từ Gradle đã cài. Server lắng nghe port 8080.

#### GET mặc định

~~~bash
curl -i http://localhost:8080/shop/api/greetings
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200
Content-Type: text/plain

Hello from Jersey
~~~

Header khác và chi tiết `charset` có thể thay đổi. Phần chắc chắn là **HTTP 200** và body `Hello from Jersey`.

#### GET với @PathParam

~~~bash
curl -i http://localhost:8080/shop/api/greetings/Linh
~~~

Kỳ vọng HTTP 200 và body:

~~~text
Hello, Linh
~~~

#### POST text/plain

~~~bash
curl -i -X POST http://localhost:8080/shop/api/greetings \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data "xin chao"
~~~

Kỳ vọng HTTP 200 với body:

~~~text
Echo: xin chao
~~~

#### Một URL sai base path

~~~bash
curl -i http://localhost:8080/greetings
~~~

Kỳ vọng không vào resource vì **thiếu `/shop/api`**. Thông thường là HTTP 404; status/body của đường không mapping có thể chịu ảnh hưởng fallback/error handler của container.

### 5.6. Ghi đè @ApplicationPath qua property

Thêm **một dòng** vào `application.properties`:

~~~properties
spring.jersey.application-path=/rest
~~~

Restart ứng dụng. Cùng `@Path("/greetings")` nay có endpoint:

~~~text
http://localhost:8080/shop/rest/greetings
~~~

Còn `/shop/api/greetings` không còn là Jersey base URL mong muốn. **Không cộng `/api` và `/rest`**; Spring Boot property ghi đè annotation.

Nếu không cần annotation trong code, có thể bỏ `@ApplicationPath` và dùng property làm **nguồn cấu hình duy nhất** cho các môi trường. Nếu cần base path cố định theo module, annotation giúp mô tả hợp đồng URL. Khi đồng thời tồn tại cả hai, nhớ ghi precedence trong tài liệu vận hành.

## 6. Test HTTP integration: kiểm tra thật Jersey servlet và context path

`@WebMvcTest`/`MockMvc` dành cho Spring MVC controllers không phải bằng chứng chắc chắn rằng JAX-RS `ResourceConfig`, Jersey ServletContainer và servlet URL mapping đã được bật đúng. Với Jersey, nên có test chạy **embedded server và HTTP thật**.

Thêm `src/test/java/demo/jersey/JerseyServletTest.java`:

~~~java
package demo.jersey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class JerseyServletTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void applicationAndResourcePathsCompose() {
        ResponseEntity<String> result = rest.getForEntity(
                "/shop/api/greetings", String.class);

        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody())
                .isEqualTo("Hello from Jersey");
    }

    @Test
    void methodPathParamIsResolved() {
        ResponseEntity<String> result = rest.getForEntity(
                "/shop/api/greetings/Linh", String.class);

        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody()).isEqualTo("Hello, Linh");
    }

    @Test
    void postUsesJaxRsConsumesAndProduces() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.TEXT_PLAIN);
        headers.setAccept(java.util.List.of(MediaType.TEXT_PLAIN));
        HttpEntity<String> request =
                new HttpEntity<>("xin chao", headers);

        ResponseEntity<String> result = rest.postForEntity(
                "/shop/api/greetings", request, String.class);

        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody()).isEqualTo("Echo: xin chao");
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.jersey.JerseyServletTest
~~~

`RANDOM_PORT` giúp test không cần cổng 8080 cố định; `TestRestTemplate` gửi HTTP đến server thật trong test context. Các test trên giả định **không đặt `spring.jersey.application-path=/rest`**; nếu đã bật override ở mục trước, phải sửa URI test theo contract mới hoặc dùng test properties để chọn profile rõ ràng.

**Điều test chứng minh:** Jersey được đăng ký như servlet, `ResourceConfig` nhìn thấy resource, DI Spring hoạt động, context path + @ApplicationPath + @Path hợp đúng, content type được xử lý. Nó chưa chứng minh hoạt động proxy/certificates phía production.

## 7. Mặc định Jersey là Servlet: cơ chế ServletRegistrationBean

Khi có `ResourceConfig` bean và `spring-boot-starter-jersey`, Spring Boot 3.3 auto-configuration mặc định tạo bean kiểu:

~~~text
ServletRegistrationBean<org.glassfish.jersey.servlet.ServletContainer>
bean name: jerseyServletRegistration
default Jersey mapping: /*
~~~

Jersey `ServletContainer` là Servlet adapter nhận HTTP requests từ container, đưa chúng vào Jersey runtime/ResourceConfig. Default mapping `/*` rất rộng nếu không đặt base path rõ.

Các property liên quan:

~~~properties
spring.jersey.type=servlet
spring.jersey.servlet.load-on-startup=1
spring.jersey.application-path=/api
~~~

- `spring.jersey.type=servlet`: chọn Servlet mode (mặc định).
- `spring.jersey.servlet.load-on-startup`: thứ tự/ưu tiên khởi tạo Servlet; mặc định `-1` nghĩa lazy initialization trong cấu hình Boot được mô tả. Đặt giá trị không âm để yêu cầu startup load phù hợp khi muốn phát hiện lỗi Jersey sớm.
- `spring.jersey.application-path`: base path, ưu tiên hơn `@ApplicationPath`.
- `spring.jersey.init.*`: cung cấp init parameters cho registration khi cần.

**Không lấy `spring.jersey.servlet.load-on-startup` để đặt timeout hay thread pool.** Nó chỉ điều khiển thời điểm khởi tạo servlet.

### Servlet mapping và Spring MVC

Giả sử cùng app có:

~~~text
DispatcherServlet: mapping /
Jersey ServletContainer: mapping /*
~~~

`/*` là prefix servlet mapping có thể được chọn trước default servlet mapping `/`. Vì thế các URL `@RestController`, static resources hoặc các routes khác có thể đi vào Jersey mà không tới MVC. Jersey trả 404 **không có nghĩa** container tự chạy tiếp DispatcherServlet; Servlet dispatch chọn servlet trước rồi mới xử lý.

**Hai cách tránh tranh chấp:**

1. Nếu Jersey và MVC **không cần chia sẻ cùng prefix**, đặt Jersey ở `/jaxrs/*` bằng `@ApplicationPath("/jaxrs")` hoặc `spring.jersey.application-path=/jaxrs`. MVC tiếp tục xử lý `/mvc/...` qua DispatcherServlet.
2. Nếu muốn Jersey **đứng trước MVC và nhường các request không phù hợp**, chuyển sang **Jersey Filter mode** và bật `FILTER_FORWARD_ON_404` như phần tiếp theo.

Một dự án phần lớn dùng JAX-RS có thể giữ Jersey servlet với mapping riêng, đơn giản hơn filter/fallback.

## 8. Jersey Filter mode: cho phép kết hợp với Spring MVC

Jersey `ServletContainer` cũng thực thi Jakarta Servlet `Filter`. Spring Boot chọn chế độ filter bằng:

~~~properties
spring.jersey.type=filter
~~~

Trong chế độ này auto-configuration tạo registration bean tên:

~~~text
jerseyFilterRegistration
type: FilterRegistrationBean<ServletContainer>
~~~

Order của filter có thể đặt qua:

~~~properties
spring.jersey.filter.order=0
~~~

**Đây là order trong servlet filter chain**, không phải thứ tự chọn JAX-RS resource hay Spring MVC controller. Nếu app có security filters, encoding, tracing hoặc request wrappers, phải test thứ tự thực tế; không chỉnh order tùy tiện chỉ để “hết 404”.

### 8.1. ResourceConfig phải có fallback-on-404 khi filter ở /*

Theo hướng dẫn Spring Boot về chạy Jersey cùng Spring MVC, cấu hình:

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.servlet.ServletProperties;
import org.springframework.stereotype.Component;

@Component
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
        property(ServletProperties.FILTER_FORWARD_ON_404, true);
    }
}
~~~

Khi Jersey xử lý request trong filter nhưng kết quả là **404 không có entity body**, property này cho phép chuyển request sang **filter tiếp theo/underlying servlet** để framework khác xử lý. Trước khi forward, Jersey có thể reset response status như tài liệu Jersey mô tả.

**Giới hạn quan trọng:**

- Chỉ có ý nghĩa khi Jersey chạy như **Filter**, không khi chạy như Servlet.
- Default của `FILTER_FORWARD_ON_404` là `false`.
- **Không phải** fallback cho mọi response 404: nếu resource/ExceptionMapper tạo 404 có entity body, behavior có thể khác.
- JAX-RS sub-resource locators hoặc code ứng dụng có thể đã được gọi trước khi Jersey quyết định không match; đừng gắn side effects vào một thao tác routing thuần.
- Nếu không có servlet nào phía sau xử lý request, chuyển tiếp vẫn không tạo được endpoint; cần Spring MVC DispatcherServlet hoặc default servlet phù hợp.

### 8.2. Biến thể B: chạy Jersey filter cùng Spring MVC

Từ dự án A, thêm dependency Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đổi `application.properties` để Jersey filter áp cho root ứng dụng, tạo cơ hội MVC nhận những URL mà Jersey không xử lý:

~~~properties
server.port=8080
server.servlet.context-path=/shop

spring.jersey.type=filter
spring.jersey.application-path=/
spring.jersey.filter.order=0
~~~

Ở `JerseyConfig` đang có `@ApplicationPath("/api")` từ dự án A, Spring Boot property `spring.jersey.application-path=/` **ghi đè** thành root. Thêm dòng `property(ServletProperties.FILTER_FORWARD_ON_404, true)` vào constructor config:

~~~java
// Snippet trong constructor JerseyConfig hiện có:
register(GreetingResource.class);
property(ServletProperties.FILTER_FORWARD_ON_404, true);
~~~

Resource `@Path("/greetings")` bây giờ có route:

~~~text
http://localhost:8080/shop/greetings
~~~

Tạo Spring MVC controller mới, trong package được component scan:

`src/main/java/demo/jersey/MvcHelloController.java`:

~~~java
package demo.jersey;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MvcHelloController {
    @GetMapping("/mvc/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }
}
~~~

Với `FILTER_FORWARD_ON_404=true`, khi gọi:

~~~bash
curl -i http://localhost:8080/shop/mvc/hello
~~~

Jersey không có JAX-RS resource `/mvc/hello`; Jersey filter nhường request cho DispatcherServlet. Kỳ vọng HTTP 200:

~~~text
Hello from Spring MVC
~~~

Còn:

~~~bash
curl -i http://localhost:8080/shop/greetings
~~~

được Jersey filter xử lý, body:

~~~text
Hello from Jersey
~~~

**Đây là thay đổi mode/config của cùng một project, không phải chạy hai registration modes một lúc.** Sau khi đổi sang Filter, các URL của test servlet A (`/shop/api/greetings`) không còn đúng; cập nhật test profile/URI tương ứng. Nếu có Spring Security hoặc custom filters, test lại auth/CSRF, filter order và error responses.

### 8.3. Khi nào không cần forward-on-404?

Nếu Jersey filter chỉ được map ở một prefix **riêng** như `/jaxrs/*` và Spring MVC xử lý các URL không thuộc prefix, request `/mvc/hello` không cần đi qua Jersey filter. Khi đó không nhất thiết dùng `FILTER_FORWARD_ON_404` cho chuyện phân tách hai namespace.

Với filter map `/*` và yêu cầu Jersey/MVC cùng dùng root, forward-on-404 là mô hình cần xem xét. Đánh đổi là routing phức tạp hơn, nguy cơ namespace collision và một số error cases khó đoán hơn.

### 8.4. Khi chỉ có Jersey filter mà không có servlet phía sau

Theo tài liệu Spring Boot, Jersey filter cần **một servlet xử lý các request mà Jersey không nhận**. Nếu app không có servlet thích hợp, có thể bật default servlet của container khi thực sự cần:

~~~properties
server.servlet.register-default-servlet=true
~~~

Đây không phải giải pháp bắt buộc nếu đã có DispatcherServlet Spring MVC. Đừng bật default servlet chỉ để “hết 404” mà không xem static-resource exposure và security policy.

## 9. Phân biệt 3 kỹ thuật đặt đường dẫn

Một hệ thống có thể đặt đường dẫn bằng code, property hoặc registration bean:

### 9.1. @ApplicationPath

~~~java
@Component
@ApplicationPath("/jaxrs")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
    }
}
~~~

Dùng khi muốn base URI ở mức code/module. Tại container root, `@Path("/greetings")` thành `/jaxrs/greetings`. Với context path `/shop` thì thành `/shop/jaxrs/greetings`.

### 9.2. spring.jersey.application-path

~~~properties
spring.jersey.application-path=/api/v2
~~~

Khi property hiện diện, nó **override** `@ApplicationPath` trên ResourceConfig. Hữu ích cho staging, versioned routing, migration hoặc cấu hình path theo môi trường. Nhớ test reverse proxy và client SDK, vì đổi path là đổi public API contract.

### 9.3. ServletRegistrationBean/FilterRegistrationBean tự khai báo

Khi default auto-registration không đủ, có thể tự đăng ký ServletContainer. Spring Boot hỗ trợ override bean tên chính xác:

- `jerseyServletRegistration` ở Servlet mode;
- `jerseyFilterRegistration` ở Filter mode.

Ví dụ **minh họa nâng cao**: chỉ dùng khi chủ động **thay** auto-registration; không ghép cùng ví dụ A nếu đã dùng property/annotation làm nguồn mapping.

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.servlet.ServletContainer;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ManualJerseyServletRegistration {
    @Bean(name = "jerseyServletRegistration")
    ServletRegistrationBean<ServletContainer> jerseyServletRegistration(
            ResourceConfig config) {

        ServletContainer servlet = new ServletContainer(config);

        ServletRegistrationBean<ServletContainer> registration =
                new ServletRegistrationBean<>(servlet, "/custom/*");

        registration.setName("customJerseyServlet");
        registration.setLoadOnStartup(1);
        return registration;
    }
}
~~~

Giả sử servlet context `/shop` và resource `@Path("/greetings")`, mapping custom `/custom/*` tạo URL dạng `/shop/custom/greetings`.

**Cảnh báo:** khi manual register, bạn đang chịu trách nhiệm về mapping, initialization, URL ownership, security và việc trùng lặp registrations. Không thêm bean này nếu đang dùng `@ApplicationPath` + property để tạo cùng registration ở path khác mà chưa biết rõ cơ chế Boot backoff. Nên ưu tiên auto-config và property trước.

Tương tự, với Filter mode có thể cung cấp `FilterRegistrationBean<ServletContainer>` tên `jerseyFilterRegistration` để đặt URL patterns/order bằng code. Nhưng để chuyển Servlet ↔ Filter trong đa số ứng dụng, chỉ cần `spring.jersey.type` và `spring.jersey.filter.order`; không viết manual registration nếu không thực sự cần.

## 10. ResourceConfig: đăng ký Resource, Provider và Feature

`ResourceConfig` không chỉ giữ các endpoint. Nó còn là nơi đăng ký:

- JAX-RS resources có `@Path`.
- `ExceptionMapper<T>` để trả response lỗi được kiểm soát.
- `ContainerRequestFilter` / `ContainerResponseFilter` cho logic request/response của Jersey.
- `MessageBodyReader` / `MessageBodyWriter` và JSON providers khi cần.
- Jersey/JAX-RS features, properties và resource lifecycle customizations.

Ví dụ:

~~~java
@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
        register(TraceHeaderFilter.class);
    }
}
~~~

`TraceHeaderFilter` phải là provider đã được triển khai. Mẫu sau là một file provider độc lập:

~~~java
package demo.jersey;

import java.io.IOException;

import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerResponseContext;
import jakarta.ws.rs.container.ContainerResponseFilter;
import jakarta.ws.rs.ext.Provider;

@Provider
public class TraceHeaderFilter implements ContainerResponseFilter {
    @Override
    public void filter(
            ContainerRequestContext request,
            ContainerResponseContext response) throws IOException {

        response.getHeaders().add("X-Jersey-Lab", "active");
    }
}
~~~

Với `register(TraceHeaderFilter.class)`, response từ Jersey resources có `X-Jersey-Lab: active`. Đây là **JAX-RS response filter bên trong Jersey**, khác Jakarta Servlet `Filter` được container đăng ký và khác Spring MVC `HandlerInterceptor`.

**Phân biệt filter theo tầng:**

| Filter | Loại | Đăng ký |
| --- | --- | --- |
| `ContainerRequestFilter` / `ContainerResponseFilter` | Jersey/JAX-RS | `ResourceConfig.register` |
| `jakarta.servlet.Filter` | Servlet web runtime | Servlet FilterRegistrationBean/@WebFilter |
| Jersey `ServletContainer` khi `spring.jersey.type=filter` | Jersey đứng như Servlet Filter | Spring Boot `jerseyFilterRegistration` |
| Spring Security `FilterChainProxy` | Nhóm Servlet security filters | Spring Security integration |

Đừng dùng `ResourceConfig.register` để “cài” một Servlet Filter mà không có cơ chế adapter tương ứng.

### 10.1. Đăng ký JSON Provider

Nếu API trả JSON DTO thay vì text/plain, hãy đảm bảo Jersey có **JAX-RS MessageBodyWriter** phù hợp (ví dụ Jersey Jackson integration). `spring-boot-starter-web` có Jackson không đồng nghĩa mọi JAX-RS serialization setup tự động giống Spring MVC `MappingJackson2HttpMessageConverter`.

Có thể thêm Jersey JSON provider dependency/phần `JacksonFeature` phù hợp phiên bản được Spring Boot quản lý và đăng ký trong `ResourceConfig`. Khi test, kiểm tra đúng `Content-Type: application/json`, serialize POJO/record, error 406/415, custom modules và thời gian/locale fields. **Không trộn version Jersey/Jackson bằng cách ép một artifact cũ không tương thích Jakarta**.

### 10.2. ResourceConfigCustomizer

Spring Boot 3.x cho phép beans triển khai `org.springframework.boot.autoconfigure.jersey.ResourceConfigCustomizer` để thêm customization trước khi Jersey sử dụng config. Ví dụ **snippet minh họa**:

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.boot.autoconfigure.jersey.ResourceConfigCustomizer;
import org.springframework.stereotype.Component;

@Component
public class JerseyLabCustomizer implements ResourceConfigCustomizer {
    @Override
    public void customize(ResourceConfig config) {
        config.property("jersey.config.server.response.setStatusOverSendError",
                        true);
    }
}
~~~

Điều này bổ sung thuộc tính mà không phải sửa trực tiếp class ResourceConfig ban đầu. Chỉ nên chọn `ResourceConfigCustomizer` khi có nhu cầu modular customization; trong ứng dụng nhỏ, register trực tiếp trong constructor thường rõ ràng hơn. Import/package của Spring Boot 4.x có thể khác Boot 3.x, nên giữ dependency/version nhất quán.

## 11. Security khi kết hợp Jersey và Spring Security

Spring Security có thể bảo vệ **cả Jersey Servlet/Filter lẫn Spring MVC** tại Servlet filter layer nếu registration và matching được cấu hình đúng. Tuy nhiên:

- `@Path` của Jersey **không tự tương đương** `@GetMapping` để Spring MVC security matcher suy ra path ownership.
- `@RolesAllowed` của Jakarta REST không nên được coi là Spring method security tự động nếu chưa có tích hợp cụ thể.
- Không dựa vào CORS/Servlet mapping như cơ chế authorization. Một client không phải browser có thể gọi API trực tiếp.
- Xác thực user/token/session phải có trước khi xử lý dữ liệu; service còn phải kiểm tra owner/tenant/resource permission.

Ví dụ cấu hình **minh họa** khi bổ sung `spring-boot-starter-security`, giả sử Jersey base `/api` và có URL công khai `/api/greetings`:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/greetings").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll());

    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Đoạn này là **snippet**, không nằm trong runnable lab A. Muốn chạy cần class `@Configuration`, imports, `@Bean` và cấu hình identity provider/password encoder. Matchers trong Spring Security thường xét đường dẫn **relative to Servlet context path**, nên `/shop` không được đưa bừa vào rule `requestMatchers("/api/**")`. Khi có nhiều servlets, MVC-specific matcher có thể cần xác định servlet path/matcher type phù hợp: **test bằng HTTP qua đúng path**.

Với Spring Security method-level authorization trên Jersey endpoints, hướng dẫn Spring Boot nhấn mạnh cấu hình response handling để Jersey dùng `setStatus(int)` thay vì `sendError(int)`, giúp Spring Security có cơ hội xử lý authentication/authorization errors trước khi response bị commit:

~~~java
// Snippet trong constructor ResourceConfig:
property("jersey.config.server.response.setStatusOverSendError", true);
~~~

Không xem property này là thay thế cho authentication/authorization; nó là **tương thích giữa xử lý status/error của Jersey và Spring Security**.

### CORS và CSRF

Nếu frontend `https://app.example.test` gọi Jersey API `https://api.example.test`, browser áp dụng CORS. CORS policy có thể được cấu hình ở Jersey resource/provider, servlet filters, reverse proxy hoặc một thành phần Spring phù hợp — **chọn một owner policy** để tránh gửi các `Access-Control-Allow-Origin` trùng/mâu thuẫn.

Khi browser dùng cookie/session, CSRF vẫn cần phân tích (SameSite, Secure, CSRF token). `spring.jersey.type=filter` không tự làm CORS preflight hoặc CSRF an toàn. Nếu Jersey filter xử lý OPTIONS trước Spring Security, thứ tự filters có thể ảnh hưởng; test preflight và actual requests qua proxy/security chain.

## 12. Context path, forwarded headers và reverse proxy

### Context path không phải application path

~~~properties
server.servlet.context-path=/shop
spring.jersey.application-path=/rest
~~~

Giả sử `@Path("/greetings")`:

~~~text
URL bên trong ứng dụng:
    /shop/rest/greetings

server.servlet.context-path:
    /shop

Jersey base path:
    /rest

Resource @Path:
    /greetings
~~~

Nếu reverse proxy công bố:

~~~text
https://example.test/services/rest/greetings
~~~

nhưng forward tới Spring:

~~~text
http://localhost:8080/shop/rest/greetings
~~~

thì mapping public/internal do reverse proxy rewrite quyết định. **Không cộng tự động `/services` vào `server.servlet.context-path`** nếu proxy đã strip hoặc rewrite prefix, nếu không dễ bị double-prefix.

Spring Boot hỗ trợ xử lý Forwarded/X-Forwarded headers qua:

~~~properties
# Chỉ bật theo thiết kế proxy được tin cậy:
server.forward-headers-strategy=framework
~~~

hoặc `native` tùy container/proxy. Đừng chấp nhận `X-Forwarded-Host`/`X-Forwarded-Proto` từ client Internet tùy ý; gateway phải strip/overwrite trước khi app trust. Redirects, absolute URLs, OAuth2 callbacks và cookie Secure có thể bị ảnh hưởng nếu sai scheme/host.

### Định tuyến nhiều ứng dụng dưới cùng hostname

Một kiến trúc thường gặp:

~~~text
https://example.test/mvc/**     -> Spring MVC DispatcherServlet
https://example.test/rest/**    -> Jersey ServletContainer
https://example.test/assets/**  -> static resource handler/CDN
~~~

Đây là cách tách namespace dễ quan sát. Nếu Jersey chạy kiểu Servlet, cố dùng `/*` cho mọi route rồi hy vọng MVC xử lý tiếp sau 404 là rủi ro. Nếu cần prefix root chung có fallback, dùng filter + `FILTER_FORWARD_ON_404` và test theo đúng semantics.

## 13. Đóng gói executable JAR/WAR và nguy cơ scanning

Jersey có khả năng package scanning hạn chế trong một số executable archives Spring Boot. Ở IDE, class files nằm trên filesystem trực tiếp; khi build, chúng có thể nằm dưới `BOOT-INF/classes` và các nested JARs của Boot executable JAR. Với executable WAR, còn có `WEB-INF/classes`. Cách scan `packages("demo.jersey")` có thể hoạt động trong IDE nhưng bỏ sót resources khi đóng gói.

Khuyến nghị:

~~~java
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
        register(TraceHeaderFilter.class);
    }
}
~~~

Đăng ký rõ các resource/provider classes. Nếu project lớn, tạo một registry module chứa danh sách class đã review hoặc một `ResourceConfigCustomizer` được tổ chức quản lý; không phụ thuộc reflection classpath scanning không được hỗ trợ ở packaging mục tiêu.

Kiểm thử hai đường:

~~~bash
./gradlew test
./gradlew bootJar
java -jar build/libs/jersey-servlet-lab-1.0.0.jar
~~~

Với `version = '1.0.0'` và `rootProject.name = 'jersey-servlet-lab'`, filename thường theo dạng `jersey-servlet-lab-1.0.0.jar`; nếu Gradle cấu hình artifact name/version khác, lấy đúng tên JAR thực tế.

Sau khi khởi động JAR đóng gói, gọi:

~~~bash
curl -i http://localhost:8080/shop/api/greetings
~~~

Nếu test trong IDE pass mà JAR trả 404, kiểm tra `ResourceConfig.register` và classpath/packaging trước khi sửa mọi controller path.

## 14. Lỗi 404, 405, 406, 415 và xung đột Servlet mapping

| HTTP status | Ngữ nghĩa thường gặp | Kiểm tra ở Jersey |
| --- | --- | --- |
| **404 Not Found** | URL không match resource hoặc bị servlet/framework khác xử lý | context path, application path, @Path, registered classes, servlet/filter mode |
| **405 Method Not Allowed** | Resource path match nhưng không hỗ trợ HTTP method đó | @GET/@POST/@PUT, method selection |
| **406 Not Acceptable** | Không đáp ứng `Accept` của client | `@Produces`, Jersey providers |
| **415 Unsupported Media Type** | Request content type không tương thích | `@Consumes` và `Content-Type` |
| **400 Bad Request** | Input/parameter conversion hoặc validation thất bại | `@PathParam`, query, DTO/body |
| **500 Internal Server Error** | Jersey init/provider/DI/business exception | stack trace server, DI, missing serializer |
| **401 Unauthorized** | Chưa xác thực, có thể từ Spring Security | SecurityFilterChain, entry point |
| **403 Forbidden** | Authorization/CSRF/CORS/filter denial | security filter order, policies |

**404 không luôn cùng nguyên nhân.** Nếu Jersey Servlet mapping `/*` chiếm URL `/mvc/hello`, Jersey có thể trả 404 trước khi DispatcherServlet chạy. Nếu Jersey filter đã bật forward-on-404, request có thể tiếp tục tới MVC và nhận 200. Nếu base path đặt sai, request không tới Jersey lần nào.

### Ba lỗi URL tiêu biểu

**Lỗi A — quên context path.**

~~~properties
server.servlet.context-path=/shop
spring.jersey.application-path=/rest
~~~

Gọi `/rest/greetings` thiếu `/shop` → không match context.

**Lỗi B — nhân đôi prefix.**

~~~java
@ApplicationPath("/api")
@Path("/api/greetings")
~~~

URL thực tế trở thành `/api/api/greetings`, không phải `/api/greetings`. Nếu muốn một prefix `/api`, resource nên là `@Path("/greetings")`.

**Lỗi C — property override annotation nhưng người viết không biết.**

~~~java
@ApplicationPath("/v1")
~~~

~~~properties
spring.jersey.application-path=/v2
~~~

Spring Boot lấy `/v2`. Các request `/v1/...` không còn match như kỳ vọng.

### 404 có body và filter fallback

Theo Jersey `ServletProperties.FILTER_FORWARD_ON_404`, chỉ khi Jersey tạo **404 không có entity body** mới forward sang filter/servlet tiếp theo. Nếu ứng dụng viết một `ExceptionMapper<NotFoundException>` trả JSON lỗi cùng 404, nó có thể **ngăn fallback**. Đừng “sửa” bằng cách nuốt mọi 404 và chuyển tiếp nếu việc đó làm lộ endpoint không được phép; tốt hơn là tách namespace rõ ràng.

## 15. Khi nào chọn Servlet, khi nào chọn Filter?

| Tiêu chí | Jersey Servlet | Jersey Filter |
| --- | --- | --- |
| Property | `spring.jersey.type=servlet` | `spring.jersey.type=filter` |
| Auto bean | `jerseyServletRegistration` | `jerseyFilterRegistration` |
| Servlet/filter layer | Jersey là servlet được container dispatch | Jersey xử lý trong filter chain |
| Mapping | Default `/*`, nên đặt prefix | Filter URL patterns/order theo configuration |
| Cùng Spring MVC | Dễ nhất khi tách prefix Jersey và MVC | Có thể nhường request qua forward-on-404 |
| Fallback sau Jersey 404 | Servlet không tự dispatch sang servlet khác | Có thể chuyển tiếp nếu `FILTER_FORWARD_ON_404=true` và 404 không có entity |
| Filter ordering | Không phải vấn đề đối với adapter Jersey như servlet | `spring.jersey.filter.order` và interactions với security/other filters |
| Init property | `spring.jersey.servlet.load-on-startup` | `spring.jersey.filter.order` |
| Resource/provider definitions | `ResourceConfig` | Cùng `ResourceConfig` |
| Servlet cần đứng sau | Không theo nghĩa fallback | Có; phải có MVC/default servlet cho đường không được Jersey xử lý |
| Độ đơn giản | Thường đơn giản cho JAX-RS API có namespace riêng | Phức tạp hơn khi tích hợp cùng MVC trên cùng root |

**Gợi ý thực tế:**

- Một API Jersey độc lập: **Servlet mode**, explicit base path `/api`.
- Cùng Spring MVC nhưng namespace tách rời: có thể dùng Jersey Servlet mapping riêng như `/jaxrs/*` và Spring MVC tại `/mvc/**`.
- Cần Jersey đứng trước các routes và fallback cho Spring MVC: **Filter mode** + `FILTER_FORWARD_ON_404`, có integration tests mạnh.
- Không có lý do cụ thể để chuyển filter: giữ default servlet, ít moving parts hơn.

## 16. Debug bằng logging và HTTP integration tests

Có thể bật logging theo nhóm web để xem registered servlet/filter patterns, theo hướng dẫn Spring Boot:

~~~properties
logging.level.web=debug
~~~

Với nhu cầu tìm lỗi sâu hơn, tạm bật log cho các packages:

~~~properties
logging.level.org.springframework.boot.autoconfigure.jersey=DEBUG
logging.level.org.glassfish.jersey=DEBUG
logging.level.org.springframework.web=DEBUG
~~~

Chỉ bật DEBUG có thời hạn trong dev/staging và kiểm soát logging PII/tokens. Không khẳng định mọi module Jersey đều phát một thông điệp cố định trên mọi version.

Checklist debug:

1. Có đúng dependency `spring-boot-starter-jersey` không?
2. Có **một ResourceConfig Spring bean** được Boot nạp không?
3. `ResourceConfig` có register đúng resource/provider classes không?
4. Resource JAX-RS có `@Path` và `@GET`/`@POST`/`@Produces`/`@Consumes` phù hợp?
5. Có dùng `jakarta.ws.rs` thay vì `javax.ws.rs` khi dự án Boot 3?
6. Jersey type là servlet hay filter? Auto bean registration nào được tạo?
7. Servlet context path hiện tại và Jersey application path là gì? Có property override `@ApplicationPath` không?
8. URL HTTP thực tế từ browser/proxy có đúng prefix và trailing slash không?
9. Nếu Jersey + MVC, có xung đột `/*` và DispatcherServlet `/` không?
10. Trong filter mode, đã bật `FILTER_FORWARD_ON_404`, có servlet đích và 404 không có entity?
11. Có filter/security chặn OPTIONS, GET, POST trước khi Jersey xử lý không?
12. Executable JAR có phát hiện resources như khi chạy IDE không?
13. Nếu 406/415, kiểm tra media types và JSON provider thay vì đổi URL bừa.
14. Có regression tests đi qua embedded HTTP server, không chỉ test controller Spring MVC?

### cURL cho đường POST hoặc media type sai

Resource lab `@Consumes(TEXT_PLAIN)`:

~~~bash
curl -i -X POST http://localhost:8080/shop/api/greetings \
  -H "Content-Type: application/json" \
  --data '{"message":"hi"}'
~~~

Dự kiến request có thể nhận **415 Unsupported Media Type**, vì resource POST nhận `text/plain`, không nhận JSON. Đừng sửa bằng cách loại `@Consumes` để nhận mọi body nếu app cần schema/validation cụ thể.

`@Produces(TEXT_PLAIN)` nhưng client gửi:

~~~bash
curl -i http://localhost:8080/shop/api/greetings \
  -H "Accept: application/xml"
~~~

có thể nhận **406 Not Acceptable** khi không có representation được chấp nhận. `curl` không gửi `Accept` rõ ràng thường chấp nhận mọi media type; khi debug cần ghi chính xác headers.

## 17. Kiểm thử khi triển khai cùng Spring MVC

Một integration test chạy container thật nên chứng minh:

~~~text
Jersey:
  GET /shop/greetings -> 200, "Hello from Jersey"

Spring MVC:
  GET /shop/mvc/hello -> 200, "Hello from Spring MVC"

Jersey không có route:
  GET /shop/other -> không bị Jersey giữ sai;
                     do MVC/default servlet xác định cuối cùng

Không hợp lệ:
  POST /shop/greetings với application/json -> 415

Bảo mật:
  API private không được bypass khi dùng filter mode
~~~

Ví dụ JUnit với Spring Boot random port (dùng **profile/filter variant** ở phần 8):

~~~java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class MixedRoutingTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void jerseyAndMvcBothRespond() {
        ResponseEntity<String> jersey =
                rest.getForEntity("/shop/greetings", String.class);

        ResponseEntity<String> mvc =
                rest.getForEntity("/shop/mvc/hello", String.class);

        assertThat(jersey.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(jersey.getBody()).isEqualTo("Hello from Jersey");

        assertThat(mvc.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(mvc.getBody()).isEqualTo("Hello from Spring MVC");
    }
}
~~~

Đây là **snippet test**, cần class package/imports từ test `JerseyServletTest` mục 6 và Gradle có starter MVC. Đừng đưa đoạn này vào project servlet-only A rồi kỳ vọng MVC controller đã tồn tại; nó dành cho **biến thể đã chuyển sang filter và thêm MvcHelloController**.

Test đủ cả 2 frameworks quan trọng hơn việc chỉ kiểm tra một HTTP 200 từ Jersey. Nếu thay `spring.jersey.application-path` giữa các environment, sử dụng test profile/config riêng và thể hiện rõ expected URL của từng profile.

## 18. Đăng ký filter/servlet thủ công: tránh double registration

Servlet `ServletContainer` và Filter `ServletContainer` đều là cách đóng gói cùng Jersey runtime, nhưng Spring Boot hỗ trợ chọn **một mode**. Những lỗi thường gặp khi custom:

- Tạo một `ServletContainer` bean và một `ServletRegistrationBean` khác nhau khiến cùng servlet có thể bị đăng ký hai lần.
- Để Boot tự tạo `jerseyServletRegistration`, đồng thời custom thêm registration cùng URL.
- Đặt tên bean custom khác `jerseyServletRegistration`/`jerseyFilterRegistration` khiến Boot không back off như kỳ vọng.
- Dùng đồng thời `@ApplicationPath`, property path và custom URL pattern mà không biết cái nào thực sự điều khiển mapping.
- Đăng ký cùng JAX-RS resource class nhiều lần dưới các scopes khác nhau làm DI, lifecycle hoặc provider behavior khó hiểu.
- Thay filter order trước Spring Security mà không kiểm tra authorization/cors/csrf.
- Đổi Servlet to Filter nhưng quên đảm bảo có DispatcherServlet/default servlet phía sau.

**Ưu tiên quy trình bảo trì được:** starter → một ResourceConfig bean → explicit registers → một base path → một mode → HTTP tests. Chỉ dùng manual `ServletRegistrationBean`/`FilterRegistrationBean` khi có yêu cầu URL/lifecycle đặc biệt chưa thể đáp ứng bằng properties.

Nếu custom bean cần điều chỉnh init parameters, có thể dùng properties đơn giản:

~~~properties
# Jersey init-param key/value supplied through Boot configuration:
spring.jersey.init.example-key=example-value
~~~

Đây chỉ minh họa cú pháp `spring.jersey.init.*`, **không phải** một option Jersey cụ thể có nghĩa nếu không có module xử lý `example-key`. Các tính năng thật cần dùng key đúng trong tài liệu Jersey.

## 19. Câu hỏi tự kiểm tra

**1.** Đã có `@Path("/hello")` nhưng URL `/hello` trả 404. Có thể kết luận resource chưa được compile không?

**Đáp án:** Không. Cần kiểm tra `ResourceConfig.register`, context path, application path, servlet/filter mapping, Spring MVC conflict và packaged JAR.

**2.** `@ApplicationPath("/api")` và `spring.jersey.application-path=/rest` được ghép thành `/api/rest`?

**Đáp án:** Không. Property ghi đè annotation; nếu context path là `/shop` và resource `@Path("/hello")` thì là `/shop/rest/hello`.

**3.** `spring.mvc.servlet.path=/mvc` có tự chuyển Jersey resources sang `/mvc`?

**Đáp án:** Không. Nó cấu hình DispatcherServlet của Spring MVC. Jersey có base path riêng.

**4.** Spring Boot mặc định tạo bean registration tên gì cho Jersey servlet?

**Đáp án:** `jerseyServletRegistration`, kiểu `ServletRegistrationBean<ServletContainer>`. Jersey default mode là servlet.

**5.** Có thể chỉ đặt `spring.jersey.type=filter` rồi mặc định MVC xử lý mọi route Jersey không match?

**Đáp án:** Không thể giả định. Với filter chặn root, cần `FILTER_FORWARD_ON_404=true` cho các 404 phù hợp, và phải có servlet phía sau nhận request.

**6.** Khi Jersey xử lý request như servlet tại `/*` rồi trả 404, có tự chuyển sang DispatcherServlet map `/`?

**Đáp án:** Không. Servlet container đã chọn servlet theo mapping; không có fallback tự động sang servlet khác chỉ vì 404.

**7.** Vì sao Spring Boot khuyên `register(MyResource.class)` thay vì `packages(...)`?

**Đáp án:** Jersey package scanning có hạn chế trong executable archives của Boot, có thể bỏ sót resources trong JAR/WAR đóng gói.

**8.** `FILTER_FORWARD_ON_404` có áp dụng khi Jersey chạy ở Servlet mode không?

**Đáp án:** Không. Theo Jersey, nó dành cho Filter mode.

**9.** Jersey resource dùng `@GET` và `@PathParam`; có phải nó được Spring MVC `@GetMapping` xử lý?

**Đáp án:** Không. Jersey/JAX-RS dispatch; Spring MVC có DispatcherServlet và annotation riêng. Spring có thể quản lý bean/resource mà không phải là framework dispatch HTTP của resource ấy.

**10.** Chuyển từ Servlet sang Filter xong, test nào quan trọng nhất?

**Đáp án:** Cả đường Jersey lẫn MVC (HTTP 200 đúng body), denied/missing routes, security, error handling, và integration qua proxy. Chỉ test một endpoint Jersey không chứng minh fallback đúng.

**11.** Nếu Spring Security method-level denial trong Jersey tạo error response sớm, nên xem thuộc tính nào?

**Đáp án:** Theo hướng dẫn Spring Boot, `jersey.config.server.response.setStatusOverSendError=true` cho Jersey dùng setStatus thay sendError, giúp security exception translation phù hợp.

**12.** Có nên dùng Servlet FilterRegistrationBean để đăng ký `ContainerResponseFilter` của Jersey?

**Đáp án:** Không trực tiếp: đây là hai tầng filter khác nhau. `ContainerResponseFilter` thuộc JAX-RS, thường đăng ký qua `ResourceConfig.register`.

## 20. Checklist áp dụng cho dự án thực tế

- [ ] Đã chọn rõ Jersey Servlet hay Jersey Filter, không vô ý đăng ký cả hai?
- [ ] Dependency `spring-boot-starter-jersey` đúng Boot major/Jakarta namespace?
- [ ] `ResourceConfig` là Spring bean và đăng ký rõ mọi resource/provider?
- [ ] Không phụ thuộc `packages(...)` mà executable JAR/WAR không hỗ trợ tốt?
- [ ] Resource JAX-RS có `@Path`, `@GET`/`@POST`, `@Produces`/`@Consumes` đúng?
- [ ] Có một nguồn chính quản lý application path; biết property override annotation?
- [ ] Context path + Jersey base path + resource path + method path ghép đúng?
- [ ] Phân biệt `spring.mvc.servlet.path` với Jersey base path?
- [ ] Nếu cùng Spring MVC, đã phân namespace hoặc cấu hình filter fallback-on-404?
- [ ] Trong filter mode, có servlet phía sau, filter order và error behavior được kiểm thử?
- [ ] Không có duplicate ServletContainer/registration beans?
- [ ] Có integration test chạy HTTP thật, cả profile servlet và filter nếu dùng?
- [ ] Có test chạy từ packaged executable JAR?
- [ ] Có test auth, CSRF, CORS, request/response filters qua thực tế deployment?
- [ ] Proxy path rewrite, forwarded headers, context path và public URL được tài liệu hóa?
- [ ] Đã quan sát 404/405/406/415 và tránh sửa mapping sai nguyên nhân?

## 21. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Servlet Web Applications: Jersey](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): ResourceConfig bean, register resources, default servlet `/*`, servlet/filter registrations, init params, executable JAR scanning.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jersey.application-path`, `spring.jersey.type`, `spring.jersey.filter.order`, `spring.jersey.servlet.load-on-startup` và `spring.jersey.init.*`.
- [Spring Boot 3.3 — JerseyAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jersey/JerseyAutoConfiguration.html): tên beans `jerseyServletRegistration`/`jerseyFilterRegistration`, conditional auto-configuration.
- [Spring Boot 3.x — Jersey How-to](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/howto.html): `FILTER_FORWARD_ON_404` khi kết hợp Spring MVC, `setStatusOverSendError` với Spring Security.
- [Jersey 3.x — ServletProperties API](https://eclipse-ee4j.github.io/jersey.github.io/apidocs/latest3x/jersey/org/glassfish/jersey/servlet/ServletProperties.html): FILTER_FORWARD_ON_404, FILTER_CONTEXT_PATH, FILTER_STATIC_CONTENT_REGEX và điều kiện xử lý 404.
- [Jersey 3.x — ServletContainer API](https://eclipse-ee4j.github.io/jersey.github.io/apidocs/latest3x/jersey/org/glassfish/jersey/servlet/ServletContainer.html): adapter vừa là Servlet vừa là Filter.
- [Jersey 3.1 User Guide](https://eclipse-ee4j.github.io/jersey.github.io/documentation/latest31x/user-guide.html): deployment model, Servlet integration và JAX-RS resources.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): auto-config security và method-level security.
- [Jakarta RESTful Web Services](https://jakarta.ee/specifications/restful-ws/): JAX-RS API và HTTP resource semantics.

**Tóm tắt quan trọng:** `ResourceConfig` quyết định **Jersey biết resource/provider nào**. `spring.jersey.type` quyết định Jersey là **Servlet** hay **Filter**. `@ApplicationPath` hoặc `spring.jersey.application-path` quyết định **base path** (property ưu tiên annotation), còn `server.servlet.context-path` bổ sung prefix của web application. Với Spring MVC cùng tồn tại, ưu tiên **tách URL namespaces** hoặc dùng **Filter + FILTER_FORWARD_ON_404** và test end-to-end.
