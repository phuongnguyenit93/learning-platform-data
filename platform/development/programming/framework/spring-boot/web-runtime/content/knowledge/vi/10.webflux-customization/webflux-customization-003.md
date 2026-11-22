# Ảnh hưởng của @EnableWebFlux và cách tùy chỉnh Spring WebFlux mà vẫn giữ Spring Boot auto-configuration

> **Phạm vi:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, **Java 17+**, ứng dụng HTTP **reactive** sử dụng `spring-boot-starter-webflux` (ví dụ mặc định chạy Reactor Netty). Mục tiêu là hiểu chính xác điều gì xảy ra khi thêm `@EnableWebFlux`, tại sao Spring Boot thường **không cần** annotation này, và nên dùng `WebFluxConfigurer`, application properties, `CodecCustomizer` hoặc `WebHttpHandlerBuilderCustomizer` trong tình huống nào. Ví dụ đầy đủ chọn Spring Boot **3.5.0** để thống nhất mã Java, Maven và cấu hình.

## 1. Vấn đề thực tế: thêm @EnableWebFlux để “bật WebFlux” có đúng không?

Trong một ứng dụng Spring Boot thông thường, chỉ cần có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

và entry point:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Khi đủ điều kiện và không có cấu hình thay thế, **Spring Boot tự cấu hình Spring WebFlux**. Bạn không phải thêm `@EnableWebFlux` để controller dùng `Mono`/`Flux` hoạt động.

Ví dụ một endpoint reactive:

~~~java
@RestController
class HelloController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("hello webflux");
    }
}
~~~

Đoạn trên chỉ là **class minh họa**, không phải file Java độc lập; cần import `Mono`, `@RestController`, `@GetMapping` và đặt nó trong project có starter WebFlux. Khi chạy WebFlux đúng stack, request `GET /hello` có thể được xử lý mà **không dùng `@EnableWebFlux`**.

Đây là một khác biệt về ý nghĩa:

- **Starter WebFlux:** đưa thư viện và cấu hình phù hợp vào classpath để Boot nhận diện và khởi tạo ứng dụng reactive.
- **`@SpringBootApplication`:** kích hoạt cơ chế auto-configuration của Spring Boot, bao gồm phần WebFlux nếu đủ điều kiện.
- **`@EnableWebFlux`:** yêu cầu Spring Framework cấu hình WebFlux trực tiếp, hướng tới **kiểm soát hoàn toàn cấu hình WebFlux**; trong ứng dụng Boot, đây **không phải** nút bật WebFlux đơn thuần.

## 2. Spring Boot tự cấu hình những gì khi không có @EnableWebFlux?

Spring WebFlux cung cấp nền tảng xử lý HTTP bất đồng bộ: `DispatcherHandler`, `HandlerMapping`, `HandlerAdapter`, `HttpMessageReader`, `HttpMessageWriter`, WebFlux.fn router, conversion/validation, v.v.

Spring Boot bổ sung tích hợp và mặc định phù hợp cho ứng dụng. Trong Boot 3.5, các nhóm đáng chú ý gồm:

1. **Cấu hình HTTP codecs**: các reader/writer cho JSON, text và các representation khác, cùng việc áp dụng cấu hình Boot liên quan đến codecs và Jackson.
2. **Static resources**: tự phục vụ tài nguyên từ các vị trí classpath như `/static`, `/public`, `/resources` và `/META-INF/resources`, hỗ trợ WebJars.
3. **Đường dẫn resource và welcome page**: kết nối những property của Boot như `spring.webflux.static-path-pattern` và các location mặc định.
4. **Tích hợp binding/formatting** với các property Boot khi thích hợp.
5. **Các cơ chế khác của hệ sinh thái Boot**: embedded reactive server, health/management, error handling, HTTP handler customizers và cấu hình riêng của từng auto-configuration.

Không phải tất cả các nhóm này đều do một class cấu hình duy nhất tạo ra. Ví dụ embedded Reactor Netty server và xử lý lỗi có các auto-configuration riêng; **không được kết luận rằng thêm `@EnableWebFlux` sẽ tự tắt toàn bộ Spring Boot**.

### Luồng thông thường

~~~text
@SpringBootApplication
        |
        v
Spring Boot kiểm tra classpath + WebApplicationType.REACTIVE
        |
        v
WebFluxAutoConfiguration (+ các auto-config liên quan)
        |
        +-- các WebFlux infrastructure bean phù hợp
        +-- codec integration theo Boot
        +-- resource mappings và welcome page theo Boot
        +-- áp dụng các WebFluxConfigurer bổ sung
        |
        v
DispatcherHandler xử lý request
        |
        +-- @RestController
        +-- RouterFunction / HandlerFunction WebFlux.fn
~~~

Điều kiện quan trọng là ứng dụng thực sự chạy **REACTIVE**. Nếu project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường chọn **Servlet MVC** khi tự nhận diện web application type. Có `WebClient` hoặc `Mono` trên classpath không chứng minh server đang dùng WebFlux.

## 3. @EnableWebFlux làm gì ở tầng Spring Framework?

Cú pháp:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class ManualWebFluxConfiguration {
}
~~~

`@EnableWebFlux` import `DelegatingWebFluxConfiguration` của Spring Framework. Lớp này dựa trên `WebFluxConfigurationSupport` để tạo các bean cấu hình WebFlux cần thiết và thu thập các bean implement `WebFluxConfigurer`.

Mô hình:

~~~text
@Configuration + @EnableWebFlux
        |
        v
Spring Framework: DelegatingWebFluxConfiguration
        |
        +-- WebFluxConfigurationSupport
        +-- RequestMappingHandlerMapping/Adapter
        +-- RouterFunctionMapping/HandlerFunctionAdapter
        +-- codec/readers/writers, conversion, validation...
        +-- delegate các WebFluxConfigurer mà project đăng ký
        |
        v
WebFlux chạy theo cấu hình framework + customization của bạn
~~~

**Điểm then chốt:** Trong ứng dụng Spring Boot, khi bạn tự khai báo cấu hình WebFlux nền tảng qua `@EnableWebFlux`, các phần **WebFlux-specific auto-configuration** của Boot sẽ **back off / không còn áp dụng như chế độ mặc định**. Vì vậy một số tùy chỉnh mặc định và property-based integrations do Boot cung cấp có thể không còn hoạt động y hệt.

Hành vi không phải “ứng dụng mất WebFlux”. Spring Framework vẫn đăng ký các thành phần cơ bản để xử lý request reactive. Khác biệt là **ai sở hữu cấu hình WebFlux**:

| Chế độ | Thành phần dẫn dắt cấu hình WebFlux | Mục tiêu |
|---|---|---|
| Boot mặc định | Spring Boot + WebFlux configuration tích hợp | Cấu hình thông dụng, áp dụng property của Boot |
| Boot + `WebFluxConfigurer`, **không** `@EnableWebFlux` | Boot giữ nền tảng, bạn bổ sung callback | Tùy chỉnh vừa phải, ít mất mặc định |
| `@EnableWebFlux` | Spring Framework `DelegatingWebFluxConfiguration` | Kiểm soát WebFlux ở mức framework |
| Kế thừa `DelegatingWebFluxConfiguration` | Project tự can thiệp bean/config ở mức sâu | Custom hoàn toàn cho tình huống đặc biệt |

Không gắn `@EnableWebFlux` theo thói quen chỉ vì tên annotation có chữ “Enable”. Nó làm **thay đổi mô hình chịu trách nhiệm cấu hình**, không đơn thuần bật một tính năng còn đang tắt.

## 4. Những thay đổi có thể quan sát sau khi thêm @EnableWebFlux

### 4.1. Static resources có thể mất hành vi tự động của Boot

Khi dùng Boot WebFlux auto-configuration, file:

~~~text
src/main/resources/static/status.txt
~~~

thường có thể được phục vụ tại `/status.txt`. Boot còn cho phép:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

để phục vụ static resource tương ứng dưới `/assets/**`. Trong chế độ Boot tiêu chuẩn, `GET /assets/status.txt` đọc file từ thư mục static mặc định.

Khi chuyển sang cấu hình WebFlux do `@EnableWebFlux` quản lý, resource mappings do **Boot** chuẩn bị có thể không còn, nên cùng URL có thể trả 404 **nếu bạn chưa tự cấu hình**. Muốn giữ resource phải thêm mapping rõ ràng bằng `WebFluxConfigurer#addResourceHandlers` hoặc cơ chế tương đương.

Điều này khác với chuyện controller JSON `GET /api/hello` còn chạy được: handler mapping annotation có thể vẫn được Spring Framework cấu hình, trong khi mapping cho file tĩnh do Boot bổ sung đã thay đổi.

### 4.2. HTTP codecs vẫn tồn tại, nhưng Boot customization không phải lúc nào cũng còn nguyên

Spring WebFlux cần `HttpMessageReader`/`HttpMessageWriter` để đọc và ghi HTTP body. `@EnableWebFlux` vẫn cung cấp cấu hình codec mặc định của **Spring Framework**, tùy classpath.

Điểm cần kiểm tra là lớp tích hợp của **Spring Boot**:

- giới hạn buffer của HTTP codecs;
- JSON/Jackson customization theo `spring.jackson.*`;
- các `CodecCustomizer` do Boot tích hợp;
- cách ứng dụng đăng ký codecs đặc biệt;
- behavior của WebClient và server codecs có cấu hình khác nhau.

**Không khẳng định “@EnableWebFlux làm JSON ngừng hoạt động”.** Nếu Jackson vẫn trên classpath, framework có thể đọc/ghi JSON bình thường. Nhưng **chi tiết cấu hình codec** có thể khác và phải được xác minh bằng test.

Trong Spring Boot 3.5, một property liên quan đến buffer là:

~~~properties
spring.http.codecs.max-in-memory-size=2MB
~~~

Property này dành cho **auto-configured WebFlux server và WebClient instances**. Không thể mặc định rằng nó tiếp tục điều khiển mọi codec bạn tự tạo trong chế độ cấu hình WebFlux thủ công. Khi tự cấu hình, nên dùng API codec cụ thể để đặt giới hạn tương ứng.

### 4.3. Các property thuộc Boot WebFlux có thể cần cấu hình lại

Những property liên quan WebFlux có thể gặp trong dự án:

~~~properties
spring.webflux.base-path=/gateway
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
spring.webflux.format.date=dd/MM/yyyy
spring.http.codecs.max-in-memory-size=2MB
~~~

Trong chế độ auto-configuration, Boot có cơ chế binding/tích hợp các property này. Khi bật `@EnableWebFlux` để nắm quyền cấu hình, bạn cần **kiểm tra từng property cụ thể** thay vì giả định mọi giá trị vẫn được Boot nối vào thành phần tương ứng.

**Không hiểu thành “mọi property Spring Boot đều vô hiệu”.** Ví dụ `server.port` thuộc cấu hình embedded web server, không phải chỉ thuộc `WebFluxAutoConfiguration`. Nó vẫn có thể hoạt động dù WebFlux request mappings được cấu hình thủ công.

### 4.4. Welcome page, WebJars, error handling và integrations

Các tính năng liên quan Boot như welcome page, WebJars resource locations, template engines, custom error response và Actuator phải được kiểm tra khi thay cách cấu hình WebFlux.

Nhưng cần phân biệt **điều kiện của từng auto-configuration**. Một số thành phần error handling hoặc management vẫn có thể được Boot quản lý bởi auto-configuration riêng. Đừng tuyên bố `@EnableWebFlux` chắc chắn tắt toàn bộ `ErrorWebExceptionHandler` hoặc làm Actuator ngừng chạy.

Cách đánh giá đáng tin là so sánh thực tế: các URL/response, bean configuration và condition evaluation giữa phiên bản trước và sau, không chỉ nhìn tên annotation.

## 5. Nên chọn cách tùy chỉnh nào? Một thang mức độ an toàn

**Ưu tiên tùy chỉnh từ mức ít xâm lấn đến mức nhiều quyền kiểm soát hơn:**

| Nhu cầu | Nên dùng trước | Có cần `@EnableWebFlux`? |
|---|---|---|
| Đổi cổng HTTP | `server.port` | Không |
| Đặt WebFlux base path | `spring.webflux.base-path` | Không |
| Đổi static URL pattern | `spring.webflux.static-path-pattern` | Không |
| Đổi vị trí file tĩnh | `spring.web.resources.static-locations` | Không |
| Điều chỉnh HTTP codec buffer theo Boot | `spring.http.codecs.max-in-memory-size` | Không |
| Bổ sung CORS cho reactive controllers | `WebFluxConfigurer#addCorsMappings` | Không |
| Thêm formatter/converter | `WebFluxConfigurer#addFormatters` | Không |
| Thêm static resource handler riêng | `WebFluxConfigurer#addResourceHandlers` | Không |
| Đổi chi tiết codec | `CodecCustomizer` hoặc `configureHttpMessageCodecs` | Không |
| Tùy chỉnh `HttpHandler` của Boot | `WebHttpHandlerBuilderCustomizer` | Không |
| Tự sở hữu toàn bộ WebFlux infrastructure | `@EnableWebFlux` + cấu hình đầy đủ | Có thể |
| Override bean cấu hình gốc của Spring Framework | Kế thừa `DelegatingWebFluxConfiguration` khi thực sự cần | Tùy kiến trúc |

Lý do của thứ tự này: càng kiểm soát sâu, bạn càng phải tự khôi phục và bảo trì những mặc định hữu ích mà Spring Boot trước đây tạo sẵn.

## 6. Cách thay thế được khuyến nghị: WebFluxConfigurer không có @EnableWebFlux

Tạo một class cấu hình:

~~~java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Authorization")
                .maxAge(1800);
    }
}
~~~

Trong ứng dụng reactive Spring Boot, class này **bổ sung CORS mapping**, còn Boot vẫn có cơ hội giữ những cấu hình mặc định khác như codecs và static resources.

Giải thích:

1. `@Configuration` khai báo bean Spring; `proxyBeanMethods=false` phù hợp khi class không dùng inter-bean method calls kiểu `@Bean`.
2. `implements WebFluxConfigurer` đăng ký callback vào cơ chế cấu hình WebFlux của framework.
3. `addCorsMappings` cấu hình quy tắc CORS cho đường dẫn `/api/**`. Ở đây chỉ origin `https://frontend.example` được phép theo ví dụ.
4. Không có `@EnableWebFlux`: **không chủ động giành quyền thay Boot WebFlux auto-configuration**.
5. CORS xử lý việc browser có cho phép ứng dụng web đọc response khác origin; **không thay thế xác thực hay phân quyền**.

Nên giới hạn origin cụ thể thay vì cho phép `*` khi ứng dụng dùng credential/cookie hoặc mang dữ liệu nhạy cảm. Khi có Spring Security reactive, phải đảm bảo CORS preflight được xử lý theo đúng thứ tự trong `SecurityWebFilterChain`; thêm callback vào MVC không phải cách sửa security cho WebFlux.

## 7. Ví dụ Spring Boot WebFlux hoàn chỉnh với Boot auto-configuration được giữ nguyên

Project dùng **Maven**, **Java 17**, **Spring Boot 3.5.0**, **Reactor Netty** qua `spring-boot-starter-webflux`. Ứng dụng có cả controller reactive, file tĩnh và CORS. Mục tiêu của bài là thấy có thể tùy chỉnh CORS mà **không dùng `@EnableWebFlux`**.

### 7.1. Cấu trúc project

~~~text
webflux-custom-demo/
  pom.xml
  src/main/java/com/example/webfluxdemo/
    WebfluxCustomDemoApplication.java
    GreetingController.java
    ApiWebFluxConfig.java
  src/main/resources/
    application.properties
    static/status.txt
  src/test/java/com/example/webfluxdemo/
    WebFluxCustomDemoIntegrationTest.java
~~~

### 7.2. `pom.xml`

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
    <artifactId>webflux-custom-demo</artifactId>
    <version>1.0.0</version>

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

Không thêm `spring-boot-starter-web` chỉ để dùng `@RestController`: cùng annotation đó được hỗ trợ bởi WebFlux, còn starter Web servlet có thể khiến Boot chọn **MVC** thay vì reactive khi tự nhận diện kiểu ứng dụng. Trong ví dụ này chỉ có starter WebFlux.

### 7.3. Entry point

`src/main/java/com/example/webfluxdemo/WebfluxCustomDemoApplication.java`:

~~~java
package com.example.webfluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxCustomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxCustomDemoApplication.class, args);
    }
}
~~~

Không có `@EnableWebFlux`. Khi có starter phù hợp, `@SpringBootApplication` là đủ để Boot tự cấu hình WebFlux.

### 7.4. Reactive controller: GET và POST JSON

`src/main/java/com/example/webfluxdemo/GreetingController.java`:

~~~java
package com.example.webfluxdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping(
        path = "/hello",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Message> hello(
            @RequestParam(defaultValue = "world") String name) {

        return Mono.just(new Message("Hello, " + name));
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Message> echo(@RequestBody Mono<Message> requestBody) {
        return requestBody.map(
                body -> new Message("Echo: " + body.message())
        );
    }

    public record Message(String message) {
    }
}
~~~

Giải thích:

- `Mono<Message>` biểu diễn một kết quả bất đồng bộ (tối đa một phần tử).
- Với GET, `@RequestParam` bind `name`; response JSON được mã hóa bởi WebFlux codec, không cần tự tạo `ObjectMapper` trong controller.
- Với POST, `@RequestBody Mono<Message>` cho WebFlux đọc JSON body theo reactive pipeline; xử lý bằng `map` mà không gọi `block()`.
- `Message` là record Java 17; tên field trong JSON là `message`.
- Mã không truy vấn DB, không dùng blocking I/O, nên phù hợp để học cơ chế cấu hình trước khi triển khai logic phức tạp.

**CORS config:** dùng nguyên file `ApiWebFluxConfig.java` ở mục 6; nó cùng package `com.example.webfluxdemo` nên được component scan. Không được thêm `@EnableWebFlux` vào file này trong nhánh ví dụ khuyến nghị.

### 7.5. Properties và tài nguyên tĩnh

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Cấu hình Boot WebFlux cho static resources.
spring.webflux.static-path-pattern=/assets/**

# Giới hạn memory buffer của HTTP codecs được Boot auto-configure.
spring.http.codecs.max-in-memory-size=2MB
~~~

`src/main/resources/static/status.txt`:

~~~text
static-ok
~~~

File `status.txt` có nội dung dòng `static-ok`. Spring Boot mặc định biết vị trí `classpath:/static/`; với pattern ở trên, URL của file là `/assets/status.txt`.

**Không có `spring.webflux.base-path`** trong ví dụ này, nhằm tách biệt ba yếu tố: route `/api/hello` là từ annotation, static prefix `/assets/**` là từ property, còn CORS path `/api/**` là từ `WebFluxConfigurer`. Các giá trị không tự cộng một cách mơ hồ.

## 8. Chạy chương trình và kiểm tra HTTP

Điều kiện: JDK 17+, Maven, cổng 8080 chưa bị chiếm.

~~~bash
mvn spring-boot:run
~~~

Hoặc:

~~~bash
mvn clean package
java -jar target/webflux-custom-demo-1.0.0.jar
~~~

### 8.1. Gọi GET JSON

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

Response body dự kiến:

~~~json
{"message":"Hello, Lan"}
~~~

Status HTTP dự kiến `200 OK`. Các header, ngày giờ và thứ tự hiển thị có thể khác theo server/client; đoạn JSON chỉ diễn tả body.

### 8.2. Gọi POST JSON

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hi"}'
~~~

Body dự kiến:

~~~json
{"message":"Echo: Hi"}
~~~

Lệnh dùng cú pháp shell Unix/Bash. Trong Windows PowerShell, có thể dùng `curl.exe` và cú pháp quoting của shell, hoặc một HTTP client khác; không copy nguyên lệnh có dấu `\` xuống dòng rồi kỳ vọng PowerShell hiểu giống Bash.

### 8.3. File tĩnh

~~~bash
curl -i "http://localhost:8080/assets/status.txt"
~~~

Response status `200`, body có dòng:

~~~text
static-ok
~~~

Đây là dấu hiệu thấy Boot static resource mapping vẫn tồn tại **cùng lúc** với lớp `WebFluxConfigurer` tùy chỉnh CORS.

### 8.4. CORS preflight

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/hello" \
  -H "Origin: https://frontend.example" \
  -H "Access-Control-Request-Method: GET"
~~~

Với cấu hình mẫu, preflight hợp lệ sẽ nhận response 2xx, trong đó header `Access-Control-Allow-Origin` có giá trị:

~~~text
https://frontend.example
~~~

Khi thay `Origin` bằng một domain không cho phép, preflight sẽ không được cấp cùng quyền CORS. Không mặc định CORS chặn mọi request từ curl/server-to-server: CORS là cơ chế phía browser, không phải cơ chế xác thực.

## 9. Integration test HTTP thực: xác nhận cả API, static resource và CORS

Dùng JDK `HttpClient` (có sẵn trong Java 17) để gửi request đến **reactive embedded server thật**, thay vì chỉ gọi method controller.

`src/test/java/com/example/webfluxdemo/WebFluxCustomDemoIntegrationTest.java`:

~~~java
package com.example.webfluxdemo;

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
class WebFluxCustomDemoIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private URI url(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @Test
    void getControllerUsesJsonCodec() throws Exception {
        assertTrue(port > 0);

        HttpRequest request = HttpRequest.newBuilder(
                url("/api/hello?name=Lan"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals(
                "{\"message\":\"Hello, Lan\"}",
                response.body());
    }

    @Test
    void postControllerReadsJsonBody() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(url("/api/echo"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"message\":\"Hi\"}"))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals(
                "{\"message\":\"Echo: Hi\"}",
                response.body());
    }

    @Test
    void bootServesStaticResource() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                url("/assets/status.txt"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("static-ok", response.body().trim());
    }

    @Test
    void webFluxConfigurerAddsCorsRule() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                url("/api/hello"))
                .header("Origin", "https://frontend.example")
                .header("Access-Control-Request-Method", "GET")
                .method("OPTIONS", HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertTrue(
                response.statusCode() >= 200 &&
                response.statusCode() < 300
        );

        assertEquals(
                "https://frontend.example",
                response.headers()
                        .firstValue("Access-Control-Allow-Origin")
                        .orElse("")
        );
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ test kiểm tra bốn điều độc lập:

1. Annotation-based controller được WebFlux route đúng.
2. JSON codec đọc và ghi body đúng.
3. Spring Boot static mapping vẫn phục vụ file qua property `spring.webflux.static-path-pattern`.
4. `WebFluxConfigurer` đã áp dụng CORS mà không cần `@EnableWebFlux`.

`@SpringBootTest(RANDOM_PORT)` mở server thật trên cổng ngẫu nhiên, còn `@LocalServerPort` được inject sau khi server khởi tạo. `mvn test` chạy test tích hợp dưới Spring Boot Test, không phải chỉ kiểm tra Mockito mock.

**Vì sao có ích?** Nếu sau này ai đó thêm `@EnableWebFlux` và mapping static do Boot không còn, test `bootServesStaticResource` sẽ phát hiện thay đổi. Điều đó có giá trị hơn kết luận dựa trên việc ứng dụng khởi động mà không báo lỗi.

## 10. Trường hợp thực sự cần @EnableWebFlux: tự phục hồi các phần đã sử dụng

Có thể có tình huống bạn muốn tự thiết kế toàn bộ WebFlux infrastructure, ví dụ một platform tùy chỉnh đặc biệt không dùng các resource mapping mặc định của Boot.

Trong tình huống đó, bạn **có thể** dùng `@EnableWebFlux`, nhưng phải chịu trách nhiệm về những thành phần mà ứng dụng thực sự cần. Dưới đây là **một cấu hình thay thế**, dùng **thay cho** `ApiWebFluxConfig.java` ở mục 6; **không đăng ký đồng thời hai class này** trong cùng project.

`src/main/java/com/example/webfluxdemo/ManualWebFluxConfig.java`:

~~~java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebFlux
public class ManualWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Authorization");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/");
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Đoạn code có các đặc điểm:

- `@EnableWebFlux` chuyển về cơ chế cấu hình Framework cho WebFlux.
- `addCorsMappings` thêm lại rule CORS mà ứng dụng cần.
- `addResourceHandlers` phục vụ `/assets/**` từ thư mục static classpath; **không giả định** property Boot tự cấu hình mapping này nữa.
- `configureHttpMessageCodecs` đặt giới hạn buffer cho **codec mặc định** bằng API Spring Framework; không giả định property của Boot vẫn được áp dụng vào mọi codec sau khi bạn quản lý WebFlux thủ công.
- Các JSON codecs mặc định còn có thể hoạt động dựa trên dependency hiện có; ví dụ này **không chủ động tắt** default codec registration.

**Quan trọng:** đây chỉ là các thành phần minh họa để giữ ba hợp đồng của project mẫu: JSON, CORS và static resources. Đây **không phải bản sao hoàn toàn** của Spring Boot WebFlux auto-configuration. Nếu dự án dùng WebJars, welcome page, template engine, error rendering, conversion, validation, multipart hoặc codec Jackson tùy chỉnh, cần xác định thêm những bean/config thích hợp.

Khi chủ đích là kiểm soát hoàn toàn Spring WebFlux, cách này có thể phù hợp, nhưng phải đo và kiểm thử các thay đổi theo từng tính năng. Với đa số API Spring Boot, giải pháp ở mục 6 ít rủi ro hơn.

## 11. Cơ chế nâng cao: DelegatingWebFluxConfiguration và HttpHandler

### 11.1. `DelegatingWebFluxConfiguration`

`@EnableWebFlux` nhập `DelegatingWebFluxConfiguration`. Đây là thành phần tập hợp `WebFluxConfigurer` và cung cấp các bean WebFlux mặc định của Spring Framework.

Nếu cần can thiệp **thấp hơn** mức callback `WebFluxConfigurer`, tài liệu Framework cho phép kế thừa trực tiếp:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.DelegatingWebFluxConfiguration;

@Configuration
public class AdvancedWebFluxConfiguration
        extends DelegatingWebFluxConfiguration {
    // Chỉ override bean/configuration khi đã hiểu cơ chế.
}
~~~

Đây là **class skeleton để minh họa chế độ advanced**, không phải cấu hình nên ghép trực tiếp với project ở mục 7. Khi chọn cách này, không đồng thời đặt `@EnableWebFlux` trên cùng class như thể cần cả hai cách; điều đó có thể tạo những định nghĩa cấu hình trùng/lẫn lộn.

Cần tự cân nhắc khi override bean như `RequestMappingHandlerMapping` hoặc `RequestMappingHandlerAdapter`. Nếu làm sai, controller có thể không được phát hiện hoặc handler không có adapter phù hợp.

### 11.2. `WebHttpHandlerBuilderCustomizer`

Đối với ứng dụng dùng Boot auto-configured `HttpHandler` nhưng cần chèn một tùy chỉnh vào cách dựng handler pipeline, Boot hỗ trợ bean `WebHttpHandlerBuilderCustomizer`. Đây là lớp tùy chỉnh chuyên biệt khác với `WebFluxConfigurer`.

Dùng nó **khi nhu cầu thật sự ở mức `WebHttpHandlerBuilder`**, chẳng hạn cần tích hợp riêng vào HTTP processing pipeline. Không dùng `@EnableWebFlux` chỉ để sửa một phần pipeline nếu Boot đã có extension point phù hợp. Những tùy chỉnh low-level phải được đánh giá với Security WebFilterChain, exception handling và request tracing; không bỏ qua các filter bảo vệ.

### 11.3. `CodecCustomizer`

Boot 3.5 có interface `org.springframework.boot.web.codec.CodecCustomizer`. Bạn có thể đăng ký bean để bổ sung/điều chỉnh `CodecConfigurer` của cơ chế auto-configuration:

~~~java
package com.example.webfluxdemo;

import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CodecSettings {

    @Bean
    CodecCustomizer bufferLimit() {
        return configurer ->
                configurer.defaultCodecs()
                          .maxInMemorySize(512 * 1024);
    }
}
~~~

Đây là **file bổ sung tùy chọn** khi cần API customization; không phải file bắt buộc của project mục 7. Nếu chọn `spring.http.codecs.max-in-memory-size` đã đáp ứng nhu cầu, đừng đặt nhiều giới hạn mâu thuẫn ở cả property và `CodecCustomizer` khi chưa xác định thứ tự/ý nghĩa override.

**Không tắt mặc định bừa bãi** bằng `configurer.registerDefaults(false)` rồi quên đăng ký lại JSON/text codec. Khi điều chỉnh sâu, hãy kiểm tra response `Content-Type`, status code, serialization và limit response body ở mức HTTP thực.

## 12. CORS, WebFilter, Security và RouterFunction: chọn đúng điểm mở rộng

### 12.1. Global CORS và per-handler CORS

WebFlux hỗ trợ cấu hình CORS thông qua callback `WebFluxConfigurer#addCorsMappings`, đồng thời một số handler annotation có thể có `@CrossOrigin`. Cần có quy ước thống nhất giữa global và local rules để tránh cho phép quá rộng.

Với router chức năng WebFlux.fn, cơ chế filter/router phù hợp có thể cần cấu hình riêng theo kiến trúc. Không mặc định mọi rule CORS thiết kế cho một nhóm annotated controller sẽ bao phủ chính xác mọi functional route và WebSocket handshake.

### 12.2. Reactive WebFilter

WebFlux dùng `org.springframework.web.server.WebFilter`. Đây là abstraction reactive tương đương ý tưởng middleware, **không phải** `jakarta.servlet.Filter` của Spring MVC.

Một `WebFilter` cho logging, correlation ID hoặc xử lý header có thể được đăng ký như Spring bean mà không cần `@EnableWebFlux`. Phần xử lý filter phải tôn trọng reactive execution model: tránh block event-loop thread bằng network/database sync calls.

### 12.3. Spring Security

Reactive Spring Security dùng `SecurityWebFilterChain`. Việc thêm hay bỏ `@EnableWebFlux` **không nên** được coi là cách bật/tắt xác thực. CORS preflight, route policy và authentication cần có test 401/403, CSRF (nếu phù hợp), credentials, origin whitelist và error responses.

Không xử lý bảo mật bằng cách biến mọi `OPTIONS` thành `200` trong application code. Hãy dùng cơ chế CORS và Security phù hợp, chỉ cho phép origin/method/header theo chính sách.

## 13. WebFlux vs Spring MVC: tránh nhầm annotation giống tên

| Chủ đề | Spring WebFlux (reactive) | Spring MVC (Servlet) |
|---|---|---|
| Starter thông dụng | `spring-boot-starter-webflux` | `spring-boot-starter-web` |
| Dispatcher | `DispatcherHandler` | `DispatcherServlet` |
| Callback bổ sung | `WebFluxConfigurer` | `WebMvcConfigurer` |
| Annotation kiểm soát đầy đủ | `@EnableWebFlux` | `@EnableWebMvc` |
| Filter | `WebFilter` | `jakarta.servlet.Filter` |
| Handler chức năng | `org.springframework.web.reactive.function.server.*` | `org.springframework.web.servlet.function.*` |
| Server mặc định trong Boot | Reactor Netty | Embedded Tomcat |
| HTTP request/response core | `ServerWebExchange` | `HttpServletRequest`/`HttpServletResponse` |

**Thêm `@EnableWebFlux` vào project MVC không đồng nghĩa chuyển project sang WebFlux**. Spring Boot xét classpath và `WebApplicationType`; khi có cả starter MVC và WebFlux, Boot mặc định thường ưu tiên MVC.

Cũng không nhầm `@EnableWebFlux` với `@EnableWebFluxSecurity` của Spring Security reactive: đó là hai mục tiêu cấu hình khác nhau.

WebFlux hỗ trợ non-blocking I/O, nhưng **không tự biến code nghiệp vụ block thành non-blocking**. Nếu handler vẫn gọi driver JDBC blocking hay `Thread.sleep` ngay trên event loop, thêm `@EnableWebFlux` không giải quyết vấn đề thread starvation.

## 14. Cách kiểm tra Boot có còn auto-configuration hay không

### 14.1. Bắt đầu từ hành vi ứng dụng

Sau khi thay config, chạy test cho:

- `GET` và `POST` JSON, status, Content-Type, conversion.
- Static resources, welcome page, WebJars URL (nếu dùng).
- Request size/codec buffer limit và cách trả lỗi khi body vượt giới hạn.
- CORS preflight và request thực.
- Error handling 404/400/415/500, Problem Details nếu bật.
- Formatting/validation, query/path binding và custom converters.
- Spring Security login/authorization, headers và filter chain.
- Base path, proxy rewrite, WebSocket/SSE, reactive context propagation.
- Health/Actuator endpoint nếu ứng dụng phụ thuộc.

Với project mẫu ở mục 7, ba hợp đồng hữu ích nhất để phát hiện thay đổi là: **JSON codec**, **static URL `/assets/status.txt`** và **CORS origin `https://frontend.example`**.

### 14.2. Condition evaluation report của Spring Boot

Có thể chạy app với `--debug` trong môi trường phát triển:

~~~bash
java -jar target/webflux-custom-demo-1.0.0.jar --debug
~~~

Spring Boot có thể in **condition evaluation report** về những auto-configuration nào match hoặc không match. Tìm các mục liên quan `WebFluxAutoConfiguration` để hiểu tại sao Boot không còn cung cấp phần MVC/reactive config bạn kỳ vọng.

`--debug` không phải công cụ chứng minh toàn bộ behavior đúng: nó chỉ giúp quan sát điều kiện cấu hình. Không nhất thiết bật DEBUG log rộng trong production vì có thể tạo lượng log lớn và lộ thông tin HTTP.

Nếu ứng dụng có Actuator, endpoint `/actuator/conditions` có thể hỗ trợ chẩn đoán nhưng phải được bảo vệ, không nên expose công khai.

### 14.3. Quan sát loại ứng dụng

Nếu log cho thấy Tomcat/Servlet MVC và `DispatcherServlet` trong một project bạn nghĩ là reactive Netty WebFlux, hãy kiểm tra dependency graph:

~~~bash
mvn dependency:tree
~~~

Tìm `spring-boot-starter-web`, `spring-boot-starter-webflux`, `spring-boot-starter-tomcat` và `spring-boot-starter-reactor-netty`. Không dùng `@EnableWebFlux` để che đi sự lựa chọn web application type không mong muốn.

### 14.4. Test scope khác nhau

`@WebFluxTest` là test slice để kiểm tra controller trong phạm vi WebFlux; nó không tự tải mọi `@Configuration` và service của ứng dụng như full context. Vì vậy có thể phải dùng `@Import` để đưa custom config vào slice test, hoặc dùng `@SpringBootTest(RANDOM_PORT)` khi muốn xác minh toàn bộ Boot auto-configuration, resource mapping và network path.

Đừng coi test chỉ khởi tạo controller thành công là bằng chứng Boot đang phục vụ static resources, codec được customize hoặc CORS preflight có hiệu lực.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng giải quyết |
|---|---|---|
| App WebFlux đã chạy nhưng được thêm `@EnableWebFlux` vì nghĩ bắt buộc | Hiểu sai vai trò annotation | Gỡ `@EnableWebFlux` nếu chỉ cần Boot mặc định |
| `GET /api/hello` chạy, nhưng `/assets/status.txt` trả 404 sau đổi config | Boot static mapping có thể đã bị thay thế | Dùng `WebFluxConfigurer` không kèm `@EnableWebFlux`, hoặc đăng ký `addResourceHandlers` |
| `spring.webflux.static-path-pattern` không còn tác động như trước | Tự quản WebFlux, property Boot không tự nối vào resource handler | Cấu hình explicit trong `ResourceHandlerRegistry` |
| Buffer limit khác dự kiến | Boot codec customization không còn áp dụng cùng cách | Kiểm tra `spring.http.codecs.*` và `ServerCodecConfigurer` đang dùng |
| JSON body lỗi 415/400 hoặc encode khác | Codec registrations hoặc media type thay đổi | Kiểm tra Jackson dependency, reader/writer, request headers, codec customizers |
| CORS preflight bị chặn | Origin/method/header chưa cho phép, hoặc Security filter khác | Cấu hình `CorsRegistry` và `SecurityWebFilterChain`, test OPTIONS thật |
| Spring Boot chạy MVC dù đã thêm WebFlux | Cả hai web starter hoặc WebApplicationType vẫn là Servlet | Rà dependency và chọn stack đúng; không dựa vào `@EnableWebFlux` |
| `@EnableWebFlux` và custom configuration class tạo bean trùng | Cấu hình WebFlux infrastructure nhiều nguồn | Chọn một mô hình chịu trách nhiệm cấu hình; không dùng cả hai advanced modes |
| Error JSON hoặc welcome page khác trước | Các Boot WebFlux extensions có thể đã thay đổi | Kiểm tra auto-config, custom error handler và resource mapping |
| Test slice pass nhưng app thật 404 | Test không load đầy đủ component/config/static resources | Dùng full `@SpringBootTest(RANDOM_PORT)` |
| Cấu hình CORS tưởng là xác thực | CORS chỉ hạn chế trình duyệt, không ngăn server clients | Áp dụng authentication/authorization riêng |
| Event loop chậm sau khi bật WebFlux | Logic blocking trong handler/filter | Dùng reactive driver hoặc cô lập blocking work vào scheduler phù hợp |

### 15.1. Không vô tình tạo cấu hình WebFlux nhân đôi

Hai đoạn sau **không nên cùng tồn tại** như hai cách “bật WebFlux”:

~~~java
@Configuration
@EnableWebFlux
class FirstConfig {
}
~~~

~~~java
@Configuration
class SecondConfig extends DelegatingWebFluxConfiguration {
}
~~~

Đây là **hai class minh họa xung đột chế độ cấu hình**, không phải source runnable của project mẫu. Nếu đăng ký nhiều cấu hình nền tảng, có thể phát sinh bean name conflicts hoặc ảnh hưởng lifecycle khó dự đoán. Hãy dùng một cách có chủ đích.

### 15.2. Không “fix” thiếu static resources bằng Controller trả file tùy tiện

Nếu file tĩnh biến mất do thiếu `ResourceWebHandler`, giải pháp đúng thường là khôi phục resource handler phù hợp. Viết `@GetMapping("/assets/**")` rồi đọc filesystem bằng đường dẫn chưa kiểm soát có thể tạo lỗi path traversal, cache và content type.

### 15.3. Không áp dụng mọi cấu hình từ MVC sang WebFlux

`WebMvcConfigurer` và `@EnableWebMvc` không cấu hình reactive HTTP handler. Dùng đúng package:

~~~java
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.config.EnableWebFlux;
~~~

Không nhầm với:

~~~java
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
~~~

Hai đoạn import trên chỉ để **so sánh package**; không thêm cả bốn dòng vào cùng project trừ khi bạn thực sự có cả hai stack và biết rõ cấu hình tương ứng.

## 16. Quy trình chuyển từ @EnableWebFlux sang cấu hình tương thích Spring Boot

Nếu project đang có `@EnableWebFlux` nhưng chỉ cần một vài tùy chỉnh, nên chuyển có kiểm soát:

1. **Khoanh vùng behavior cần giữ:** tất cả controller routes, WebFlux.fn routes, CORS, codecs, static resources, error formats, WebSocket/SSE, validation và filter/security.
2. **Xác định phần tùy chỉnh thực sự cần:** ví dụ chỉ `addCorsMappings`, thêm converter, đổi static resource prefix.
3. **Chuyển cấu hình đơn giản sang properties:** `spring.webflux.static-path-pattern`, `spring.web.resources.static-locations`, `spring.http.codecs.max-in-memory-size`, v.v. theo đúng phiên bản Boot.
4. **Chuyển callback bổ sung sang `WebFluxConfigurer`:** giữ `@Configuration` nhưng **bỏ `@EnableWebFlux`**.
5. **Chuyển codec customizations nếu cần:** xem `CodecCustomizer` hoặc `configureHttpMessageCodecs`; tránh viết lại toàn bộ default codecs.
6. **Chạy regression tests trước khi xóa cấu hình thủ công:** tránh mất các formatter, resource handlers, global CORS hoặc bean đặc thù mà dự án đang cần.
7. **Kiểm tra condition report:** xác nhận Boot WebFlux auto-configuration áp dụng như dự kiến, không có bean manual nào khiến nó tiếp tục back off.
8. **Triển khai theo môi trường:** verify cả URL sau proxy/ingress, headers CORS, error response và telemetry trước khi chuyển production.

Không tự xóa ngay `@EnableWebFlux` trong một ứng dụng lớn nếu nó được dùng để override nhiều bean gốc: trước hết cần lập danh sách các override, thiết kế cách thay thế và có test xác minh.

## 17. Checklist lựa chọn và kiểm tra cuối

- [ ] Project thật sự dùng **Spring WebFlux reactive**, không phải MVC chỉ thêm WebClient.
- [ ] Có `spring-boot-starter-webflux` và một cấu hình `@SpringBootApplication` phù hợp.
- [ ] **Không thêm `@EnableWebFlux`** nếu chỉ muốn sử dụng WebFlux với Boot mặc định.
- [ ] Những thay đổi đơn giản đã dùng Boot properties khi có thể.
- [ ] Tùy chỉnh WebFlux bổ sung dùng `WebFluxConfigurer` **không có `@EnableWebFlux`**.
- [ ] Codec tuning dùng property `spring.http.codecs.*` hoặc Boot `CodecCustomizer` khi cần.
- [ ] CORS được cấu hình cụ thể, không thay cho authentication/authorization.
- [ ] Có test controller JSON, static resources, CORS và format lỗi.
- [ ] Nếu dùng `@EnableWebFlux`, đã cấu hình lại đúng những resource/codec/formatter cần và hiểu mình đang tự quản phần WebFlux.
- [ ] Không kết luận tất cả Spring Boot auto-configuration đã bị vô hiệu; chỉ đánh giá những class và bean thật sự liên quan.
- [ ] Có regression tests trước/sau và khả năng rollback khi thay cấu hình reactive.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): mô tả WebFlux auto-configuration, codecs, static resources, `WebFluxConfigurer` và `@EnableWebFlux`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.codecs.max-in-memory-size`, `spring.webflux.static-path-pattern`, `spring.web.resources.static-locations`.
- [Spring Framework 6.2 — WebFlux Config](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): `@EnableWebFlux`, `WebFluxConfigurer`, `DelegatingWebFluxConfiguration`, CORS, codecs và resources.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest` và `@SpringBootTest`.
- [Spring Boot 3.5 — WebFluxAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html): API/auto-config WebFlux cụ thể của Spring Boot.
- [Spring Framework 6.2 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): reactive request processing.

**Kết luận:** Trong Spring Boot, `@EnableWebFlux` không phải “annotation bắt buộc để chạy reactive”. Nó chuyển quyền sở hữu phần cấu hình WebFlux từ các tích hợp tiện dụng của Spring Boot sang cấu hình framework do ứng dụng quản lý. Với đa số project, **giữ Boot auto-configuration, thêm `WebFluxConfigurer` không có `@EnableWebFlux` và dùng những property/extension points phù hợp** là cách đạt mục tiêu với ít rủi ro nhất. Chỉ dùng `@EnableWebFlux` khi thực sự chủ động nắm cấu hình WebFlux toàn diện và đã kiểm thử lại toàn bộ behavior liên quan.
