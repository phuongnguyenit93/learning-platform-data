# Thiết lập spring.webflux.base-path và ánh xạ tài nguyên trong Spring WebFlux

Spring WebFlux cho phép tổ chức URL của toàn bộ ứng dụng dưới một tiền tố chung, đồng thời quyết định URL nào dùng để phục vụ CSS, JavaScript, ảnh, tài liệu và WebJars. Spring Boot hỗ trợ các nhu cầu này bằng những property riêng; khi cần ánh xạ bổ sung, ứng dụng có thể dùng WebFluxConfigurer mà vẫn giữ auto-configuration của Boot.

Bài học tập trung vào bốn câu hỏi:

1. spring.webflux.base-path thêm tiền tố gì cho HTTP endpoint?
2. spring.webflux.static-path-pattern quyết định URL của file tĩnh như thế nào?
3. spring.web.resources.static-locations quyết định tìm file ở đâu?
4. Khi nào cần WebFluxConfigurer.addResourceHandlers và làm sao kiểm thử để tránh 404, trùng tiền tố hoặc lộ file?

Ví dụ dùng Spring Boot **3.5.16**, Spring WebFlux, Java 17+ và embedded Reactor Netty. Một số tên package hoặc behavior có thể thay đổi ở các phiên bản lớn khác. Luôn tra tài liệu của phiên bản được quản lý bởi dự án.

## 1. Ba khái niệm cần phân biệt

| Cấu hình | Nó thay đổi điều gì? | Ví dụ giá trị | Tác động dự kiến |
|---|---|---|---|
| spring.webflux.base-path | Tiền tố chung của các web handler trong ứng dụng reactive | /app | GET /api/ping trở thành GET /app/api/ping ở bên ngoài |
| spring.webflux.static-path-pattern | Mẫu URL dành cho tài nguyên tĩnh của Boot | /assets/** | File site.css có thể được truy cập qua /assets/site.css trước khi ghép base path |
| spring.web.resources.static-locations | Danh sách vị trí tìm file tĩnh | classpath:/static/ | Quyết định thư mục chứa site.css, không phải URL công khai |
| spring.webflux.webjars-path-pattern | Mẫu URL riêng cho nội dung WebJars | /webjars/** | Phục vụ assets trong dependency đóng gói theo cấu trúc WebJar |
| WebFluxConfigurer.addResourceHandlers | Ánh xạ bổ sung do ứng dụng khai báo | /manual/** → classpath:/manual/ | Thêm đường dẫn tải tài liệu ngoài default static mapping |

**Base path là phần tiền tố của URL bên ngoài; path pattern là điều kiện chọn request; resource location là vị trí lấy bytes của tài nguyên.** Chúng không phải ba cách khác nhau để đặt cùng một biến.

Ví dụ khi cấu hình:

~~~yaml
spring:
  webflux:
    base-path: /app
    static-path-pattern: "/assets/**"
~~~

và có file src/main/resources/static/site.css, URL bên ngoài thường là:

~~~text
http://localhost:8080/app/assets/site.css
~~~

Không cần tạo thư mục src/main/resources/static/app/assets. Hai đoạn /app và /assets nằm ở **không gian URL**, còn file thật vẫn có thể nằm dưới **classpath:/static/**.

## 2. Luồng request và cách ghép đường dẫn

Có thể hình dung một request đi qua các tầng:

~~~text
Client: GET /app/assets/site.css
           |
           v
Embedded reactive HTTP server (Reactor Netty)
           |
           v
WebFlux base path: /app
           |
           v
Path dùng để match web handler: /assets/site.css
           |
           v
Resource handler pattern: /assets/**
           |
           v
ResourceWebHandler tra classpath:/static/site.css
           |
           v
HTTP response: CSS
~~~

Với controller /api/ping, request tương ứng là GET /app/api/ping. Với functional router GET /fn/ping, request tương ứng là GET /app/fn/ping. Base path áp dụng cho các handler thuộc WebFlux application, không chỉ cho phương thức @GetMapping.

**Không khai báo lại /app trong @RequestMapping, RouterFunctions.route(), hay addResourceHandler** chỉ vì đã đặt spring.webflux.base-path=/app. Nếu thêm tay cả hai nơi, rất dễ tạo URL /app/app/... hoặc route không match như mong đợi.

Một bảng kiểm tra nhanh:

| Định nghĩa bên trong ứng dụng | URL ở client khi base path=/app |
|---|---|
| @GetMapping("/api/ping") | /app/api/ping |
| RouterFunction.GET("/fn/ping") | /app/fn/ping |
| Boot static-path-pattern="/assets/**", file static/site.css | /app/assets/site.css |
| addResourceHandler("/manual/**"), file manual/guide.txt | /app/manual/guide.txt |
| Không có base path (mặc định) | Không thêm /app |

Bảng này dành cho một ứng dụng Spring Boot WebFlux chạy trên cùng cổng HTTP; reverse proxy, gateway hoặc management server ở cổng khác có thể tạo thêm tiền tố riêng và cần kiểm tra theo kiến trúc thực tế.

## 3. spring.webflux.base-path không phải server.servlet.context-path

Spring MVC chạy trên Servlet stack thường dùng:

~~~properties
server.servlet.context-path=/app
~~~

Spring WebFlux reactive application sử dụng:

~~~properties
spring.webflux.base-path=/app
~~~

Hai property thuộc **hai mô hình ứng dụng khác nhau**. Nếu đang chạy một Spring Boot WebFlux app chỉ có spring-boot-starter-webflux, đừng dựa vào server.servlet.context-path để đổi URL reactive.

Nếu thêm cả spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot thông thường ưu tiên MVC/Servlet, trừ khi cấu hình application type rõ ràng. Khi đó WebFlux base path có thể không mang lại kết quả mong đợi vì ứng dụng không còn dùng WebFlux server theo thiết kế ban đầu.

Với Spring WebFlux server, không có lý do phải khai báo @EnableWebFlux chỉ để bật base-path. Spring Boot đọc property và cấu hình web application theo cơ chế auto-configuration.

### 3.1. Base path không phải cơ chế bảo mật

Thêm /app không ngăn người khác gọi endpoint; nó chỉ đổi vị trí endpoint trong URL. Authentication, authorization, TLS, CORS và rate limiting vẫn là trách nhiệm riêng. Một static resource được phục vụ công khai dưới /app/assets vẫn phải được xem là tài nguyên truy cập công khai, trừ khi đã có chính sách bảo vệ thích hợp.

### 3.2. Base path không đổi port và host

server.port quyết định cổng HTTP của embedded server; spring.webflux.base-path quyết định phần đường dẫn. Với server.port=8080 và base-path=/app, địa chỉ minh họa là http://localhost:8080/app/..., không phải một server mới.

## 4. Ánh xạ tài nguyên tĩnh mặc định

Spring Boot hỗ trợ tài nguyên tĩnh trong WebFlux thông qua ResourceWebHandler và resource handling của framework. Theo mặc định, những vị trí classpath thường được xét là:

- classpath:/META-INF/resources/
- classpath:/resources/
- classpath:/static/
- classpath:/public/

Ví dụ file:

~~~text
src/main/resources/static/site.css
src/main/resources/static/images/logo.svg
~~~

Khi không đổi static-path-pattern và không có base path, các file có thể được phục vụ ở:

~~~text
/site.css
/images/logo.svg
~~~

Mặc định spring.webflux.static-path-pattern là /**. Điều đó khiến resource handler có phạm vi URL rộng, nhưng không có nghĩa nó tự tạo ra mọi file; request tới tên file không tồn tại vẫn có thể bị 404.

Nếu muốn tách API và tài nguyên rõ ràng, có thể đặt:

~~~yaml
spring:
  webflux:
    static-path-pattern: "/assets/**"
~~~

Khi đó file static/site.css được phục vụ theo /assets/site.css thay vì /site.css. Thêm base-path=/app thì đường dẫn bên ngoài thành /app/assets/site.css.

**Tài liệu nhắc tới /static, /public, /resources và /META-INF/resources là thư mục nguồn trên classpath**, không phải bốn prefix URL mặc định. Tạo file static/js/app.js không buộc URL phải là /static/js/app.js.

## 5. Thay resource location khác với thay URL pattern

Hai property thường bị nhầm:

~~~properties
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
~~~

Ý nghĩa:

- URL pattern /assets/** quyết định **request nào** có thể được ánh xạ tới resource handler.
- Location classpath:/static/ quyết định **nơi tìm bytes** sau khi resource handler tách phần đường dẫn tương đối.

Ví dụ file trên classpath là static/css/site.css, với base /app và static pattern /assets/** thì URL là /app/assets/css/site.css.

### 5.1. Ghi đè static-locations sẽ thay thế danh sách mặc định

Nếu đặt:

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
        - "classpath:/shared-assets/"
~~~

ứng dụng không tự giữ đồng thời mọi location mặc định. Nếu vẫn muốn dùng static/ thì phải thêm "classpath:/static/" vào danh sách. Hành vi welcome page detection cũng phụ thuộc các location mới; nếu index.html ở thư mục cũ không còn trong danh sách, trang chào có thể không được phát hiện như trước.

Để **thêm một route tài nguyên riêng mà không thay default static locations**, thường nên dùng WebFluxConfigurer.addResourceHandlers, thay vì thay thế toàn bộ danh sách bằng static-locations.

### 5.2. Vị trí classpath khác đường dẫn filesystem

- classpath:/static/ đọc tài nguyên được đóng gói trong JAR hoặc classpath runtime.
- file:/opt/app/assets/ đọc một thư mục filesystem bên ngoài, nếu ứng dụng và môi trường cho phép.
- src/main/resources/static/ là đường dẫn trong **source tree**; khi build, nó thường trở thành classpath:/static/.

Dùng filesystem location cho nội dung user-upload hoặc nội dung thay đổi thường xuyên đòi cân nhắc quyền truy cập, thay đổi file, backup và an toàn đường dẫn. Không nên cho ResourceWebHandler phục vụ trực tiếp thư mục có secret hoặc dữ liệu nhạy cảm.

## 6. Dự án mẫu đầy đủ: API, RouterFunction và hai nhóm tài nguyên

Ví dụ đặt ứng dụng tại /app; API controller ở /api/ping, functional route ở /fn/ping; static assets của Boot dùng /assets/**; một thư mục tài liệu riêng dùng /manual/**. Tất cả đều nằm dưới /app khi client truy cập.

Dự án dùng **Spring Boot 3.5.16**, **Java 17+**, Maven. Chỉ dùng spring-boot-starter-webflux cho reactive web server; không thêm spring-boot-starter-web.

Cấu trúc:

~~~text
webflux-path-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/pathdemo/
    │   │   ├── PathDemoApplication.java
    │   │   ├── ApiController.java
    │   │   ├── FunctionalRoutes.java
    │   │   └── ExtraResourceConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       ├── static/site.css
    │       └── manual/guide.txt
    └── test/
        └── java/com/example/pathdemo/PathMappingTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>webflux-path-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>webflux-path-demo</name>

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

Spring Boot parent quản lý các phiên bản dependency. Maven cần kết nối tới kho dependency phù hợp trong lần build đầu nếu local cache chưa có thư viện.

### 6.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /app
    static-path-pattern: "/assets/**"
~~~

Không khai báo spring.web.resources.static-locations, vì dự án muốn **giữ nguyên các vị trí static mặc định** của Boot rồi chỉ bổ sung một resource handler cho tài liệu.

### 6.3. PathDemoApplication.java

~~~java
package com.example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathDemoApplication.class, args);
    }
}
~~~

### 6.4. ApiController.java

~~~java
package com.example.pathdemo;

import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

Định nghĩa của controller **không chứa /app**. Khi client gọi /app/api/ping, Spring Boot áp dụng base path rồi WebFlux khớp /api/ping với @RequestMapping và @GetMapping.

### 6.5. FunctionalRoutes.java

~~~java
package com.example.pathdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> pingRoute() {
        return RouterFunctions.route(
                RequestPredicates.GET("/fn/ping"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("fn-ok"));
    }
}
~~~

Định nghĩa route cũng **không chứa /app**. Bên ngoài, client gọi /app/fn/ping. WebFlux.fn dùng ServerRequest và ServerResponse; nó không yêu cầu một controller annotation.

### 6.6. ExtraResourceConfiguration.java

~~~java
package com.example.pathdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraResourceConfiguration implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manual/**")
                .addResourceLocations("classpath:/manual/")
                .setCacheControl(CacheControl.noCache());
    }
}
~~~

Điều này thêm mapping mới: /manual/** đọc dữ liệu ở classpath:/manual/. Việc thêm WebFluxConfigurer **không đòi @EnableWebFlux** và không nên kèm @EnableWebFlux nếu mục tiêu là giữ resource/codec auto-configuration của Spring Boot.

CacheControl.noCache() hướng trình duyệt/cache phải revalidate trước khi dùng bản được lưu, không có nghĩa tuyệt đối không được lưu response; nếu tài liệu có bí mật cần cơ chế authorization và cache no-store phù hợp hơn.

### 6.7. Các file tài nguyên

**src/main/resources/static/site.css**

~~~css
body {
    color: #234567;
    font-family: sans-serif;
}
~~~

**src/main/resources/manual/guide.txt**

~~~text
This guide is served by an extra WebFlux resource mapping.
~~~

Sau khi build, site.css là tài nguyên trên classpath:/static/, còn guide.txt nằm ở classpath:/manual/. Không tạo thư mục app/assets hoặc app/manual trong source tree.

### 6.8. Chạy ứng dụng

Từ thư mục webflux-path-demo:

~~~bash
mvn test
mvn spring-boot:run
~~~

Các request có thể kiểm tra bằng curl:

~~~bash
curl -i http://localhost:8080/app/api/ping
curl -i http://localhost:8080/app/fn/ping
curl -i http://localhost:8080/app/assets/site.css
curl -i http://localhost:8080/app/manual/guide.txt
~~~

Kết quả kỳ vọng:

| Request | Status | Nội dung đáng kiểm tra |
|---|---|---|
| GET /app/api/ping | 200 | JSON có status bằng ok |
| GET /app/fn/ping | 200 | Body fn-ok |
| GET /app/assets/site.css | 200 | CSS chứa color: #234567 |
| GET /app/manual/guide.txt | 200 | Văn bản hướng dẫn từ manual/ |
| GET /api/ping | 404 | Thiếu base path /app |
| GET /app/site.css | 404 | Thiếu prefix tài nguyên /assets |
| GET /app/app/api/ping | 404 | Lặp base path ngoài thiết kế |

Ví dụ body API:

~~~json
{"status":"ok"}
~~~

Server log, thứ tự header và kiểu chi tiết của 404 tùy runtime nên không được coi là một output cố định. Điều nên xác nhận là HTTP status, Content-Type và phần body có ý nghĩa.

## 7. Integration test bằng WebTestClient

Cách kiểm tra đáng tin là khởi động ứng dụng thực trên random port và gọi các URL mà client sẽ dùng. WebTestClient có thể được Boot cấu hình cho WebFlux application.

**src/test/java/com/example/pathdemo/PathMappingTest.java**

~~~java
package com.example.pathdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PathMappingTest {

    @Autowired
    private WebTestClient client;

    @Test
    void annotatedApiUsesBasePath() {
        client.get()
                .uri("/app/api/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void functionalRouteUsesBasePath() {
        client.get()
                .uri("/app/fn/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("fn-ok");
    }

    @Test
    void bootStaticResourceUsesBothPrefixes() {
        client.get()
                .uri("/app/assets/site.css")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body)
                        .contains("color: #234567"));
    }

    @Test
    void additionalResourceMappingIsAccessible() {
        client.get()
                .uri("/app/manual/guide.txt")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body)
                        .contains("extra WebFlux resource mapping"));
    }

    @Test
    void missingOrDuplicatedPrefixDoesNotMatch() {
        client.get().uri("/api/ping")
                .exchange().expectStatus().isNotFound();

        client.get().uri("/app/app/api/ping")
                .exchange().expectStatus().isNotFound();

        client.get().uri("/app/site.css")
                .exchange().expectStatus().isNotFound();
    }
}
~~~

Bài test kiểm tra đồng thời annotation, RouterFunction, static resources của Boot, custom ResourceHandler và ba URL sai. Nó cho thấy base-path không buộc ứng dụng phải sửa từng mapping thủ công.

Chạy:

~~~bash
mvn test
~~~

Khi các test pass, Maven trả exit code 0. Không hard-code kết quả log hoặc cổng random; hãy đánh giá assertion thay vì số port in ra. Nếu dùng proxy ở production, cần thêm smoke test qua proxy để xác minh URL bên ngoài thực tế.

## 8. Khi chỉ muốn đổi URL tài nguyên mà không đổi API

Nếu API cần tiếp tục ở /api/ping nhưng CSS/JS nên chuyển từ /site.css sang /assets/site.css, không dùng spring.webflux.base-path; hãy chỉ cấu hình:

~~~yaml
spring:
  webflux:
    static-path-pattern: "/assets/**"
~~~

Lúc đó:

- @GetMapping("/api/ping") vẫn ở /api/ping.
- File static/site.css chuyển sang /assets/site.css.
- Không có prefix /app cho toàn ứng dụng.

Đây là cách làm chính xác hơn khi requirement chỉ liên quan đường dẫn của assets.

Ngược lại, nếu muốn **tất cả** endpoint và tài nguyên đặt dưới /app thì dùng base-path, kết hợp với static-path-pattern nếu muốn thêm nhóm /assets rõ ràng.

## 9. Khi chỉ muốn đổi nguồn file, không đổi URL

Nếu URL vẫn là /assets/site.css nhưng file nằm trong một thư mục khác trên classpath, cấu hình location:

~~~yaml
spring:
  webflux:
    base-path: /app
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
        - "classpath:/static/"
~~~

File classpath:/frontend/site.css hoặc classpath:/static/site.css có thể được tìm khi request /app/assets/site.css, theo thứ tự và quy tắc resource resolver đang áp dụng.

Không nhầm location với URL: classpath:/frontend/ không tạo URL /frontend/ trừ khi path pattern cũng được đặt tương ứng.

**Chú ý việc thay thế mặc định:** nếu đặt static-locations chỉ có frontend/, file ở default public/ có thể không còn được phục vụ. Nếu muốn thêm một nhóm file độc lập, dùng addResourceHandlers như ví dụ thay vì thay danh sách gốc.

## 10. Khi nào nên dùng WebFluxConfigurer.addResourceHandlers?

Dùng khi cần một mapping chuyên biệt mà các property toàn cục không biểu đạt tốt, chẳng hạn:

- /manual/** đọc từ classpath:/manual/ với chính sách cache riêng.
- /downloadable-docs/** đọc từ một location đã được kiểm soát với content type/cache policy thích hợp.
- Một nhóm assets cần ResourceResolver/ResourceTransformer hoặc versioning riêng.
- Phục vụ nhiều namespace URL với nguồn tài nguyên và chính sách khác nhau.

Ví dụ khác về cache (chỉ minh họa, không thay class trong dự án mẫu):

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/vendor/**")
            .addResourceLocations("classpath:/vendor/")
            .setCacheControl(CacheControl.maxAge(
                    7, java.util.concurrent.TimeUnit.DAYS));
}
~~~

Các điểm cần cân nhắc:

1. Mẫu đường dẫn ở addResourceHandler viết theo **không gian handler nội bộ**, không chèn base-path /app.
2. Dùng pattern hẹp như /manual/**, tránh tự tạo /** chồng lên mặc định.
3. Resource location nên kết thúc bằng / để đường dẫn tương đối được giải quyết rõ ràng.
4. Cache policy phải phù hợp với khả năng thay đổi file; assets có tên versioned có thể cache lâu hơn.
5. Không mở thư mục chứa config, keystore, upload private hoặc file secret ra HTTP.
6. Không cấu hình @EnableWebFlux chỉ vì cần một resource handler bổ sung.

Một custom handler không phải giải pháp thay toàn bộ Spring Boot static configuration; nếu chỉ cần đổi prefix dùng static-path-pattern, nếu chỉ cần đổi source dùng static-locations.

## 11. WebJars có đường dẫn riêng

WebJars đóng gói thư viện frontend trong dependency JAR theo cấu trúc WebJar. Với Spring Boot và dependency phù hợp, tài nguyên có thể được phục vụ qua URL thuộc namespace WebJars.

Property:

~~~properties
spring.webflux.webjars-path-pattern=/vendor/**
~~~

điều chỉnh pattern dành cho WebJars, không phải static-path-pattern chung. Khi có base-path=/app thì client dùng tiền tố /app trước URL WebJars do cấu hình tương ứng tạo ra.

Không nên dùng spring.web.resources.static-locations để đoán thay đổi vị trí file bên trong WebJar. Đường dẫn cuối cùng và việc bỏ hoặc giữ đoạn version phụ thuộc dependency, cách đóng gói WebJar và khả năng resolution. Hãy kiểm tra URL thực tế bằng HTTP test.

Nếu ứng dụng không dùng WebJars thì không cần cấu hình nhóm property này.

## 12. Welcome page và SPA fallback

Spring Boot hỗ trợ phát hiện index.html trong những static resource locations được cấu hình và có thể dùng nó làm welcome page khi không có route khác phù hợp. Khi thay static-locations, tập thư mục để tìm welcome page cũng thay đổi.

Tuy nhiên, không nên mặc định coi welcome page và static-path-pattern là cùng một cơ chế. Khi đổi pattern sang /assets/**, hành vi truy cập /app/ và /app/assets/index.html có thể cần được kiểm thử riêng tùy mapping, thứ tự handler và cấu hình ứng dụng. Bài mẫu chỉ dựa vào những URL file cụ thể, không dựa vào một SPA fallback ngầm.

**Single Page Application:** frontend thường muốn /app/dashboard và /app/settings trả index.html, sau đó client-side router xử lý. Đây là một requirement riêng, không được tự động hoàn thành chỉ nhờ spring.webflux.base-path hoặc static-path-pattern.

Với SPA fallback, hãy:

- Giữ API và asset namespace rõ ràng.
- Chỉ forward/serve index.html cho các route frontend hợp lệ.
- Không biến mọi 404 API thành 200 HTML, vì điều đó che lỗi.
- Đảm bảo các path như /api/**, /assets/** và /actuator/** không bị fallback sai.
- Kiểm thử direct refresh tại đường dẫn sâu của SPA và lỗi 404 API.

WebFlux.fn có hỗ trợ routing tới static resources theo predicate, nhưng đó là một giải pháp routing bổ sung, không phải hệ quả tự động của base-path.

## 13. Actuator và cổng quản trị: tránh đoán nhầm prefix

Nếu ứng dụng thêm Spring Boot Actuator, đường dẫn quản trị có property riêng:

~~~properties
management.endpoints.web.base-path=/actuator
~~~

Khi management endpoint dùng **cùng HTTP port** với WebFlux application, management.endpoints.web.base-path được tính tương đối với spring.webflux.base-path. Ví dụ base-path=/app và management base-path=/actuator thì URL được mong đợi là /app/actuator/health, nếu endpoint health được expose và security cho phép.

Khi dùng **management.server.port** riêng, management endpoints được cấu hình tương đối theo management.server.base-path trên cổng quản trị. Không nên tự ghép /app vào URL management port trong trường hợp này.

Việc đổi base path có thể ảnh hưởng health check của ingress/load balancer nếu nó gọi sai đường dẫn. Sau deployment, kiểm tra cả URL ứng dụng và đường dẫn health thực sự được dùng.

Actuator không nằm trong dependency dự án mẫu; thêm management properties riêng sẽ không tự tạo health endpoint khi chưa có starter cần thiết.

## 14. Base path sau reverse proxy hoặc API gateway

Có ba bên có thể thay đổi phần path:

1. Client gửi URL công khai, ví dụ /edge/app/api/ping.
2. Reverse proxy/ingress có thể giữ nguyên path hoặc bỏ prefix /edge.
3. Spring Boot WebFlux áp dụng base path trên path mà server thực sự nhận.

Nếu proxy **bỏ /edge** trước khi forward, Spring Boot nhận /app/api/ping và base-path=/app là phù hợp.

Nếu proxy **giữ nguyên /edge/app/api/ping**, phải cấu hình route/rewrite nhất quán với path mà ứng dụng nhận. Không tự thêm /edge vào spring.webflux.base-path mà chưa biết proxy làm gì.

Forwarded headers như Forwarded hoặc X-Forwarded-Prefix có thể ảnh hưởng việc xác định URL bên ngoài tùy strategy và hạ tầng. Cấu hình server.forward-headers-strategy phải dựa trên proxy đáng tin cậy; không nên tin mọi header do client tự gửi. Những URL absolute trong redirect, CORS callback, cookie Path và tài nguyên CSS/JS là những chỗ dễ phát sinh lỗi khi deploy dưới prefix.

### 14.1. Tại sao localhost chạy đúng nhưng production 404?

Một số nguyên nhân:

- Ingress route đã thêm /app nhưng ứng dụng cũng tự thêm /app trong controller.
- Proxy strip prefix khác với kỳ vọng.
- Frontend build ra URL tuyệt đối /assets/site.css trong khi ứng dụng thực ở /app/assets/site.css.
- CDN hoặc reverse proxy cache URL cũ sau khi đổi static-path-pattern.
- Security filter hoặc CORS config đang match pattern theo URL cũ.
- Health probe vẫn gọi /actuator/health trong khi endpoint thực ở /app/actuator/health.

Điều cần làm là ghi rõ một **bảng URL đầu-cuối**: public URL, path sau proxy, path WebFlux nhận, handler pattern nội bộ và resource location.

## 15. Mapping order, 404 và những lỗi dễ che giấu

WebFlux dùng nhiều HandlerMapping để chọn handler. Annotation controllers, functional routers và resource handlers đều tham gia xử lý request, nhưng route specificity và thứ tự mapping có quy tắc riêng. Không nên coi file tĩnh luôn được ưu tiên hơn API hoặc ngược lại trong mọi cấu hình tùy biến.

Khi static-path-pattern mặc định là /**, một request không khớp controller có thể đi vào ResourceWebHandler. Nếu file không tồn tại, kết quả cuối cùng vẫn có thể là 404 nhưng exception/log khác một route hoàn toàn không match. Với pattern hẹp /assets/**, việc phân biệt API và resource URL thường dễ quan sát hơn.

**Mẫu đường dẫn không phải đường dẫn filesystem.** Cấu hình /assets/** không có nghĩa URL có thể đọc tùy ý các file bất kỳ trên ổ đĩa; WebFlux resource resolver vẫn tìm trong các location đã cấu hình. Tuy vậy, nếu tự mở một filesystem root quá rộng, nguy cơ lộ tài nguyên là có thật.

Khi gặp lỗi hãy kiểm tra theo thứ tự:

1. HTTP request đang gọi port, host, scheme và path nào?
2. Có reverse proxy nào strip hoặc thêm prefix không?
3. Spring Boot thực sự đang chạy **reactive WebFlux**, hay đang chạy Spring MVC vì starter khác?
4. spring.webflux.base-path có đúng không?
5. Request pattern nội bộ là @GetMapping, RouterFunction hay static-path-pattern?
6. Resource location có thực sự chứa file sau khi đóng gói JAR?
7. Cấu hình spring.web.resources.add-mappings có vô hiệu hóa default mapping không?
8. Có security rule chặn request bằng 401/403 trước khi handler xử lý không?
9. Có SPA fallback hoặc custom router chiếm URL quá rộng không?
10. Test trực tiếp tới app port và test qua ingress có cùng kết quả không?

Bật log có chọn lọc trong môi trường thử nghiệm có thể hỗ trợ xem các mapping được đăng ký. Không bật logging request/body quá chi tiết với credential hoặc dữ liệu cá nhân trong production.

## 16. Cache-Control, ETag và phiên bản tài nguyên

Resource handling hỗ trợ cache headers và cơ chế resource chain. Các lựa chọn phổ biến:

- CSS/JS có tên file gắn version hoặc content hash có thể cache lâu khi deployment quản lý version.
- HTML entrypoint thường cần thời gian cache ngắn hơn vì nó tham chiếu tới assets của phiên bản mới.
- Tài nguyên thường xuyên thay đổi nên có chính sách revalidation hoặc no-store tùy độ nhạy cảm.
- ResourceWebHandler có thể xử lý Last-Modified và yêu cầu conditional GET, tùy location và cấu hình.

Spring Boot expose nhiều property trong nhóm spring.web.resources.cache.* và spring.web.resources.chain.*. Với một namespace tài nguyên riêng có nhu cầu khác, addResourceHandlers có thể khai báo cache policy riêng.

Một cấu hình chung minh họa:

~~~yaml
spring:
  web:
    resources:
      cache:
        cachecontrol:
          max-age: 1h
~~~

Đây là cơ chế cache cho các resource handler do Boot cấu hình, không thay chính sách của một handler đã chủ động setCacheControl trong Java. Không áp dụng TTL dài cho tất cả static responses mà chưa xem cách invalidation, versioning và chính sách dữ liệu.

## 17. Bảo mật tài nguyên và giới hạn triển khai

Một resource handler rất tiện để phục vụ ảnh, CSS hoặc tài liệu công khai, nhưng cần nhớ:

- **Không đặt credentials, config secrets, backup database, khóa riêng hoặc dữ liệu khách hàng** trong location được phục vụ tĩnh.
- Resource location ngoài JAR cần file permissions và kiểm soát symlink/đường dẫn phù hợp.
- Static resource dưới /app không tự trở thành private chỉ vì URL có prefix.
- Nếu cần tài liệu theo quyền người dùng, nên phục vụ qua controller/service có kiểm tra authorization, tránh expose toàn bộ thư mục.
- Với Spring Security WebFlux, cấu hình SecurityWebFilterChain theo URL công khai và base path thực tế; test request chưa xác thực, không chỉ test client đã đăng nhập.
- Nên kiểm tra Content-Type, X-Content-Type-Options, cache headers và chính sách tải xuống đối với loại file có thể nguy hiểm.
- Thay static-path-pattern có thể làm hỏng các đường dẫn frontend hard-code, manifest, source map và service worker scope; cần kiểm tra trong browser thực.

Spring WebFlux application không dựa vào src/main/webapp theo cách của Servlet WAR. Với executable JAR, dùng src/main/resources/... để đóng gói static content; đừng kỳ vọng thư mục webapp không được package sẽ được phục vụ tự động.

## 18. Tổng hợp tình huống và quyết định cấu hình

| Nhu cầu | Giải pháp nên ưu tiên |
|---|---|
| Toàn bộ API và assets cần nằm dưới /app | spring.webflux.base-path=/app |
| Chỉ chuyển CSS/JS sang /assets/** | spring.webflux.static-path-pattern="/assets/**" |
| Giữ URL nhưng đổi thư mục tìm assets | spring.web.resources.static-locations |
| Thêm /manual/** với nguồn riêng và cache riêng | WebFluxConfigurer.addResourceHandlers |
| Chỉ đổi đường dẫn WebJars | spring.webflux.webjars-path-pattern |
| Tách cổng health/metrics | management.server.port và management.server.base-path, khi có Actuator |
| Ứng dụng Spring MVC/Servlet | Xem server.servlet.context-path và spring.mvc.static-path-pattern, không dùng công thức WebFlux y nguyên |
| Chạy sau gateway | Xác nhận rewrite rules và forwarded headers trước khi chỉnh base path |

## 19. Checklist trước khi triển khai

- [ ] Có spring-boot-starter-webflux, xác định ứng dụng thật sự chạy WebFlux/DispatcherHandler.
- [ ] spring.webflux.base-path được đặt với một prefix rõ ràng, không viết lặp vào controller/router.
- [ ] spring.webflux.static-path-pattern được hiểu là URL pattern, không phải thư mục file.
- [ ] spring.web.resources.static-locations chỉ bị ghi đè khi đã xác định cần thay default locations.
- [ ] Các static files thật sự có mặt trong JAR/classpath runtime.
- [ ] Resource handler tùy chỉnh dùng WebFluxConfigurer, không thêm @EnableWebFlux khi muốn giữ Boot defaults.
- [ ] API, RouterFunction, assets và custom mapping đều có HTTP test với URL đầy đủ.
- [ ] Có test cho path thiếu prefix, lặp prefix và URL static cũ không còn phù hợp.
- [ ] Asset URL trong HTML/JS/CSS được xây dựng phù hợp base path.
- [ ] Đã rà soát proxy rewrite, forwarded headers, CDN và health probes.
- [ ] Security và caching được thiết kế riêng; base path không phải authorization.
- [ ] Không dùng static resource mapping để xuất dữ liệu cần phân quyền.

## 20. Ghi nhớ

**spring.webflux.base-path** quyết định tiền tố chung của web handlers trong Spring Boot WebFlux. **spring.webflux.static-path-pattern** quyết định những URL nào thuộc cơ chế phục vụ static resources của Boot. **spring.web.resources.static-locations** quyết định nơi đọc file. **WebFluxConfigurer.addResourceHandlers** dùng khi cần thêm một nhóm ánh xạ riêng.

Ví dụ với base-path=/app và static-path-pattern=/assets/**, file classpath:/static/site.css có URL /app/assets/site.css. Không nhân đôi /app trong @GetMapping, RouterFunction hoặc addResourceHandler. Kiểm thử cả đường dẫn đúng và đường dẫn sai là cách đáng tin để phát hiện lỗi ghép prefix khi deploy.

## Tài liệu chính thức

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Framework 6.2 — WebFlux Config: Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Boot — Monitoring over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
