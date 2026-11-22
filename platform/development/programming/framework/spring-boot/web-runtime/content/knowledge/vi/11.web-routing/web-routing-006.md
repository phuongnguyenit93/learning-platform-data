# Định tuyến chức năng với WebMvc.fn và phân biệt API với WebFlux.fn

## 1. Mục tiêu: định tuyến HTTP bằng hàm thay vì annotation

Spring Framework có hai mô hình lập trình HTTP song song với @Controller và @RequestMapping:

- **WebMvc.fn**: functional endpoints thuộc **Spring Web MVC**, vận hành trên Servlet stack và DispatcherServlet. Handler là một hàm nhận ServerRequest và trả về ServerResponse **trực tiếp**, theo hợp đồng đồng bộ.
- **WebFlux.fn**: functional endpoints thuộc **Spring WebFlux**, vận hành trên reactive stack và DispatcherHandler. Handler là một hàm nhận ServerRequest và trả về **Mono<ServerResponse>**, theo hợp đồng reactive.

Hai API cố ý dùng những tên khái niệm rất giống nhau: RouterFunction, HandlerFunction, ServerRequest, ServerResponse, RequestPredicates và RouterFunctions. Tuy nhiên, các kiểu dữ liệu thuộc **những package khác nhau**, hợp đồng trả về khác và không thể hoán đổi chỉ bằng cách đổi dependency.

Trong WebMvc.fn, developer khai báo đường dẫn và HTTP method thành một RouterFunction, rồi chỉ định HandlerFunction nhận request tương ứng. Spring MVC tự phát hiện RouterFunction bean trong ApplicationContext và tích hợp với quá trình dispatch bình thường.

Ví dụ ý tưởng:

~~~text
GET /api/items/42
    |
    v
RouterFunction: tìm predicate phù hợp
    |
    v
HandlerFunction: xử lý ServerRequest
    |
    v
ServerResponse: ghi status, header và body
~~~

Với WebFlux.fn, thứ tự khái niệm tương tự nhưng phần tìm handler và phần tạo response gắn với Publisher/Mono và reactive request pipeline.

Bài này dùng **Spring Boot 3.5.x, Spring Framework 6.2.x và Java 17+** cho ví dụ. Phần code của WebMvc.fn và WebFlux.fn thuộc **hai dự án riêng** để tránh lẫn web stack. Khi chuyển sang phiên bản khác, cần đối chiếu package và API theo tài liệu tương ứng.

## 2. Bảng so sánh nhanh WebMvc.fn và WebFlux.fn

| Khía cạnh | WebMvc.fn | WebFlux.fn |
|---|---|---|
| Framework | Spring Web MVC | Spring WebFlux |
| Starter Boot điển hình | spring-boot-starter-web | spring-boot-starter-webflux |
| Package gốc | org.springframework.web.servlet.function | org.springframework.web.reactive.function.server |
| HTTP dispatch | DispatcherServlet | DispatcherHandler |
| API mô tả route | RouterFunction<ServerResponse> | RouterFunction<ServerResponse> trong package reactive |
| Hợp đồng HandlerFunction | ServerResponse handle(ServerRequest) | Mono<ServerResponse> handle(ServerRequest) |
| Đọc request body | request.body(Type.class), thường đồng bộ | request.bodyToMono(Type.class), reactive |
| Tạo response body đơn giản | ServerResponse.ok().body(value) | ServerResponse.ok().bodyValue(value), trả Mono<ServerResponse> |
| Phù hợp thư viện blocking | Có thể dùng theo mô hình Servlet, cần quản lý thread và timeout | Không block event-loop; ưu tiên reactive I/O, cô lập blocking khi bất khả kháng |
| Bộ test điển hình | MockMvc | WebTestClient |
| Tích hợp trong Boot | MVC auto-configuration | WebFlux auto-configuration |
| Bảo mật điển hình | Servlet Spring Security FilterChain | Reactive SecurityWebFilterChain |

Cùng một đoạn như RouterFunctions.route().GET(...) có thể tồn tại trong cả hai mô hình. **Không xác định stack dựa trên tên RouterFunctions**, hãy nhìn package import, loại ApplicationContext và starter đang hoạt động.

WebMvc.fn không phải “bản cũ” của WebFlux.fn, cũng không phải cách chạy reactive trên Servlet. Nó là functional programming model của Spring MVC, dùng request và response type thân thiện với lập trình hàm nhưng vẫn thuộc lifecycle Servlet.

## 3. Các thành phần cốt lõi

### RouterFunction

RouterFunction nhận một ServerRequest và tìm HandlerFunction phù hợp bằng RequestPredicate. Nó tương đương trách nhiệm ánh xạ URL và HTTP method, nhưng cách biểu diễn là mã Java thay vì annotation.

Trong WebMvc.fn, về mặt khái niệm:

~~~java
Optional<HandlerFunction<ServerResponse>> route(ServerRequest request);
~~~

Trong WebFlux.fn, về mặt khái niệm:

~~~java
Mono<HandlerFunction<ServerResponse>> route(ServerRequest request);
~~~

Đây là các chữ ký giải thích sự khác biệt kiểu trả về, không phải hai interface tự định nghĩa. Trong code ứng dụng, thường dùng RouterFunctions.route() builder thay vì tự implement RouterFunction.

### HandlerFunction

HandlerFunction nhận ServerRequest và tạo response:

~~~java
// WebMvc.fn: minh họa chữ ký đồng bộ
ServerResponse handle(ServerRequest request) throws Exception;
~~~

~~~java
// WebFlux.fn: minh họa chữ ký reactive
Mono<ServerResponse> handle(ServerRequest request);
~~~

Với MVC, handler có thể trả ServerResponse ngay sau khi hoàn tất xử lý. Với WebFlux, Mono đại diện cho response bất đồng bộ; việc có Mono không tự chứng minh mọi bước bên trong là non-blocking nếu code vẫn gọi database/JDBC đồng bộ trên event-loop.

### ServerRequest và ServerResponse

ServerRequest cung cấp cách truy cập path variable, query parameter, header và request body. ServerResponse là abstraction xây response, ví dụ HTTP 200, 201, 400, 404, Content-Type và body.

Hai cặp ServerRequest/ServerResponse **không cùng class**, dù tên trùng. Các import tương ứng là:

~~~java
// MVC:
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
~~~

~~~java
// WebFlux:
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
~~~

Khi IDE tự import nhầm package, lỗi compilation có thể xuất hiện ở kiểu RouterFunction, HandlerFunction hoặc giá trị trả về của lambda.

### RequestPredicates

RequestPredicates cung cấp các điều kiện match theo HTTP method, path, Accept, Content-Type và những thuộc tính khác. Có thể kết hợp bằng and(), or() hoặc negate(). Ví dụ route chỉ dành cho GET request chấp nhận JSON:

~~~java
.GET("/api/items/{id}",
        RequestPredicates.accept(MediaType.APPLICATION_JSON),
        handler::find)
~~~

RequestPredicate kiểm tra metadata HTTP, không thay thế validation của request body. Một request có Accept không phù hợp có thể không match chính route cụ thể đó; không nên suy đoán trước luôn nhận 406 hay 404 nếu chưa xem toàn bộ HandlerMappings và exception handling thực tế.

## 4. WebMvc.fn được đăng ký vào Spring Boot thế nào?

Trong Spring Boot sử dụng spring-boot-starter-web, thông thường bạn chỉ cần khai báo một bean RouterFunction<ServerResponse> trong một @Configuration được component-scan.

~~~text
Spring Boot MVC application
        |
        +--> @Configuration khai báo RouterFunction bean
        |
        v
RouterFunctionMapping dò các RouterFunction beans
        |
        v
HandlerFunctionAdapter thực thi HandlerFunction
        |
        v
DispatcherServlet tiếp tục vòng đời response MVC
~~~

Spring MVC infrastructure nhận biết các RouterFunction beans. Không cần tự tạo DispatcherServlet, HandlerFunctionAdapter hoặc một HTTP server mới chỉ để dùng functional routes.

Có thể dùng WebMvc.fn **song song với @RestController** trong cùng ứng dụng Spring MVC. Chúng là hai cách mô tả handler cho cùng Servlet-based request pipeline. Tuy nhiên, không nên khai báo hai endpoint trùng method/path rồi giả định Spring chọn route theo độ cụ thể toàn cục: nhiều HandlerMapping có thứ tự khác nhau và cả sự ưu tiên giữa functional/annotated mapping có thể khiến một bên thắng ngoài ý muốn. Hãy tránh duplicate route và viết integration test.

**Không thêm @EnableWebMvc chỉ để kích hoạt WebMvc.fn** trong Spring Boot. Boot starter đã tích hợp MVC functional endpoints; @EnableWebMvc chuyển sang tự kiểm soát phần lớn MVC configuration và có thể làm mất auto-configuration mặc định hữu ích của Boot.

## 5. Ví dụ hoàn chỉnh: WebMvc.fn với Spring Boot 3.5

### 5.1. Tạo dự án MVC

Tạo dự án Spring Boot **3.5.x, Java 17+** có các dependencies Maven:

~~~xml
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
~~~

Đây là phần dependencies bên trong một pom.xml đã có Spring Boot parent hoặc BOM dependency management và phần build cơ bản. Starter web đưa Spring MVC và một embedded servlet server phù hợp, thường là Tomcat.

Các file chính:

~~~text
src/main/java/example/mvcfn/
    MvcFnApplication.java
    MvcItemHandler.java
    MvcRoutes.java
src/test/java/example/mvcfn/
    MvcRoutesTest.java
~~~

### 5.2. Application

Tệp src/main/java/example/mvcfn/MvcFnApplication.java:

~~~java
package example.mvcfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcFnApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFnApplication.class, args);
    }
}
~~~

@SpringBootApplication cần đặt ở package cha để component scan tìm các @Component và @Configuration trong ví dụ.

### 5.3. Handler đồng bộ

Tệp src/main/java/example/mvcfn/MvcItemHandler.java:

~~~java
package example.mvcfn;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class MvcItemHandler {

    public ServerResponse featured(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("id", "featured",
                             "name", "Featured item"));
    }

    public ServerResponse find(ServerRequest request) {
        String id = request.pathVariable("id");

        if (!"42".equals(id)) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("id", id, "name", "Example item"));
    }

    public ServerResponse create(ServerRequest request)
            throws Exception {

        Map<?, ?> input = request.body(Map.class);
        Object rawName = input.get("name");

        if (!(rawName instanceof String name) || name.isBlank()) {
            return ServerResponse.badRequest()
                    .body(Map.of("error", "name is required"));
        }

        return ServerResponse.status(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("id", "43", "name", name));
    }
}
~~~

Đặc điểm:

- find đọc id bằng request.pathVariable("id") và trả ServerResponse **trực tiếp**, không trả Mono.
- create dùng request.body(Map.class) để đọc JSON request body trong Servlet environment. Tùy cấu hình HTTP message converter, JSON không hợp lệ có thể được chuyển thành client error qua xử lý exception của MVC.
- Map chỉ để ví dụ gọn; trong ứng dụng thực nên dùng DTO và validation chặt chẽ.
- id 42 tồn tại theo logic giả lập; những id khác trả 404. POST trả một đối tượng minh họa với id 43 nhưng **không lưu database**; do đó không coi endpoint là hệ thống CRUD thật.

### 5.4. RouterFunction bean

Tệp src/main/java/example/mvcfn/MvcRoutes.java:

~~~java
package example.mvcfn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RequestPredicates;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class MvcRoutes {

    @Bean
    RouterFunction<ServerResponse> itemRoutes(
            MvcItemHandler handler) {

        return RouterFunctions.route()
                .GET("/api/items/featured",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::featured)
                .GET("/api/items/{id}",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::find)
                .POST("/api/items",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
    }
}
~~~

Handler được inject vào @Bean method. Không cần đăng ký handler class bằng @Controller hay @RestController vì nó là một @Component bình thường được gọi bởi functional routing.

Thứ tự route có chủ đích: **/api/items/featured trước /api/items/{id}**. Nếu route động /{id} đứng trước, chữ featured có thể bị coi là id và route cụ thể phía sau không bao giờ có cơ hội chạy trong router đó.

POST dùng contentType(APPLICATION_JSON) để giới hạn request body media type theo ý định ví dụ. GET dùng accept(APPLICATION_JSON) để chấp nhận request mong muốn nhận JSON. Cả hai điều kiện là RequestPredicate, không phải phương pháp xác thực.

### 5.5. Chạy thử

Chạy ở thư mục project:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Nếu ứng dụng không override server.port, Boot thông thường lắng nghe port 8080.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/42
~~~

Response HTTP 200 với JSON body tương đương:

~~~json
{"id":"42","name":"Example item"}
~~~

Thứ tự key trong JSON có thể khác vì dùng Map; không dựa vào byte-for-byte JSON để kiểm thử nội dung.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/featured
~~~

Dự kiến nhận id=featured và name=Featured item, do route cụ thể được đặt trước.

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook"}'
~~~

Dự kiến status 201, JSON chứa id=43 và name=Notebook. Không phải thao tác ghi dữ liệu thật.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/999
~~~

Dự kiến status 404 vì handler find tự trả notFound khi id khác 42.

## 6. Kiểm thử WebMvc.fn với MockMvc

Trong ứng dụng servlet MVC, MockMvc tích hợp thuận tiện với DispatcherServlet và RouterFunctionMapping. Tệp src/test/java/example/mvcfn/MvcRoutesTest.java:

~~~java
package example.mvcfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcRoutesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void findItem() throws Exception {
        mvc.perform(get("/api/items/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("42"))
                .andExpect(jsonPath("$.name").value("Example item"));
    }

    @Test
    void moreSpecificRouteWins() throws Exception {
        mvc.perform(get("/api/items/featured")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("featured"));
    }

    @Test
    void missingItemReturns404() throws Exception {
        mvc.perform(get("/api/items/999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());
    }

    @Test
    void createItem() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Notebook\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Notebook"));
    }

    @Test
    void blankNameReturns400() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Mẫu kiểm thử khởi động ApplicationContext MVC thật nhưng không cần mở socket HTTP thông thường. Nó đủ để xác nhận các RouterFunction beans được nhận, request predicates hoạt động và handler trả status/body mong muốn.

Chạy:

~~~bash
./mvnw test
~~~

Nếu bổ sung Spring Security, MockMvc request có thể nhận 401/403 trước khi tới handler; khi đó phải cấu hình test user, policy hoặc security phù hợp thay vì kết luận router hỏng.

## 7. WebFlux.fn: cùng cách diễn đạt route, khác hợp đồng thực thi

WebFlux.fn sử dụng các tên khái niệm giống WebMvc.fn nhưng thuộc reactive package. Không chuyển MVC handler sang WebFlux bằng cách chỉ đổi return thành Mono và giữ import servlet.

Các khác biệt có thể thấy ngay:

~~~java
// WebMvc.fn:
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;
~~~

~~~java
// WebFlux.fn:
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;
~~~

Hàm xử lý reactive thường dùng request.bodyToMono(...), flatMap(...), ServerResponse.bodyValue(...), body(Publisher, Class), Mono.error(...) hoặc các operator Reactor phù hợp để xây pipeline.

Khi handler trả Mono<ServerResponse>, việc tạo giá trị response có thể được trì hoãn tới lúc publisher được subscribe. Đây là mô hình xử lý khác với MVC handler trả ServerResponse trực tiếp. Với I/O non-blocking, reactive pipeline giúp quản lý tài nguyên và áp lực downstream hiệu quả; nhưng một cuộc gọi Thread.sleep hoặc JDBC.blocking trong event-loop vẫn gây vấn đề.

### Sơ đồ WebFlux.fn

~~~text
HTTP request
    |
    v
Reactive HTTP server / Reactor Netty (thường dùng với Boot)
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    v
RouterFunctionMapping -> HandlerFunctionAdapter
    |
    v
Mono<ServerResponse>
    |
    v
ServerResponseResultHandler ghi response bằng Publisher
~~~

WebFlux.fn và WebMvc.fn đều có thể chạy cùng annotated controllers thuộc stack của chính mình. Sự hiện diện của functional routes không loại bỏ cơ chế @RestController tương ứng.

## 8. Ví dụ WebFlux.fn trong dự án Spring Boot riêng

### 8.1. Dependency và cấu trúc

Tạo **dự án thứ hai** với Spring Boot 3.5.x, Java 17+, dùng spring-boot-starter-webflux và spring-boot-starter-test:

~~~xml
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
~~~

Dự án này **không khai báo spring-boot-starter-web**. Nếu có cả hai starter, Spring Boot thường chọn MVC theo quy tắc suy luận web application type; có WebFlux.fn classes trong classpath không đủ chứng minh ứng dụng đang dùng reactive runtime.

Các file:

~~~text
src/main/java/example/fluxfn/
    FluxFnApplication.java
    FluxItemHandler.java
    FluxRoutes.java
src/test/java/example/fluxfn/
    FluxRoutesTest.java
~~~

### 8.2. Application

Tệp src/main/java/example/fluxfn/FluxFnApplication.java:

~~~java
package example.fluxfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxFnApplication {

    public static void main(String[] args) {
        SpringApplication.run(FluxFnApplication.class, args);
    }
}
~~~

Không cần @EnableWebFlux trong Spring Boot khi chỉ muốn dùng WebFlux.fn với auto-configuration mặc định.

### 8.3. Reactive handler

Tệp src/main/java/example/fluxfn/FluxItemHandler.java:

~~~java
package example.fluxfn;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class FluxItemHandler {

    public Mono<ServerResponse> featured(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("id", "featured",
                                  "name", "Featured item"));
    }

    public Mono<ServerResponse> find(ServerRequest request) {
        String id = request.pathVariable("id");

        if (!"42".equals(id)) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("id", id, "name", "Example item"));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(Map.class)
                .flatMap(input -> {
                    Object rawName = input.get("name");

                    if (!(rawName instanceof String name)
                            || name.isBlank()) {
                        return ServerResponse.badRequest()
                                .bodyValue(
                                        Map.of("error",
                                               "name is required"));
                    }

                    return ServerResponse.status(HttpStatus.CREATED)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(
                                    Map.of("id", "43", "name", name));
                })
                .switchIfEmpty(
                        ServerResponse.badRequest()
                                .bodyValue(
                                        Map.of("error",
                                               "body is required")));
    }
}
~~~

Đây là bản reactive tương ứng với logic giả lập MVC:

- find trả Mono<ServerResponse> ngay cả khi dữ liệu lấy từ bộ nhớ và kết quả đã biết.
- create đọc body bằng bodyToMono(Map.class) rồi xử lý bằng flatMap, không gọi block().
- Khi body rỗng và bodyToMono hoàn tất không có phần tử, switchIfEmpty tạo response 400 thay vì trả Mono.empty() không tạo response.
- Việc serialize Map thành JSON phụ thuộc các codecs do WebFlux auto-configuration đăng ký; spring-boot-starter-webflux cung cấp hạ tầng mặc định.
- Trong hệ thống thật, Mono cần kết nối với các lời gọi reactive I/O như R2DBC hoặc WebClient khi thích hợp; không bọc một blocking repository trong Mono.just rồi giả định đã non-blocking.

### 8.4. Reactive RouterFunction bean

Tệp src/main/java/example/fluxfn/FluxRoutes.java:

~~~java
package example.fluxfn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FluxRoutes {

    @Bean
    RouterFunction<ServerResponse> itemRoutes(
            FluxItemHandler handler) {

        return RouterFunctions.route()
                .GET("/api/items/featured",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::featured)
                .GET("/api/items/{id}",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::find)
                .POST("/api/items",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
    }
}
~~~

So sánh với class MvcRoutes, số lượng method và ý định route giống nhau, nhưng **các import RouterFunctions, RequestPredicates, RouterFunction và ServerResponse khác hoàn toàn**. Method reference handler::find cũng trả Mono<ServerResponse>, không phải ServerResponse.

### 8.5. Chạy và thử bằng curl

~~~bash
./mvnw spring-boot:run
~~~

Trong ví dụ đơn giản trên, app chạy cổng 8080 nếu chưa thay đổi cấu hình. Không chạy đồng thời hai dự án MVC và WebFlux trên cùng host/port nếu không đổi cổng của một trong hai.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/42
~~~

Dự kiến 200, JSON chứa id=42 và name=Example item.

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook"}'
~~~

Dự kiến 201, JSON chứa id=43 và name=Notebook. HTTP response quan sát được có thể giống ví dụ MVC nhưng **cơ chế xử lý bên trong khác**.

## 9. Kiểm thử WebFlux.fn với WebTestClient

Tệp src/test/java/example/fluxfn/FluxRoutesTest.java:

~~~java
package example.fluxfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FluxRoutesTest {

    @Autowired
    WebTestClient client;

    @Test
    void findItem() {
        client.get()
                .uri("/api/items/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.name").isEqualTo("Example item");
    }

    @Test
    void moreSpecificRouteWins() {
        client.get()
                .uri("/api/items/featured")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("featured");
    }

    @Test
    void createItem() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"Notebook\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Notebook");
    }

    @Test
    void missingItem() {
        client.get()
                .uri("/api/items/999")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void blankName() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"\"}")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

WebTestClient gửi request tới reactive server trong full Spring Boot test context với random port, kiểm tra status và JSON body. Nó không yêu cầu các handler dùng blocking I/O. Test này có cùng tình huống với MockMvc test nhưng dựa vào stack khác.

Với các route thuần functional, cũng có thể dùng WebTestClient.bindToRouterFunction(routerFunction) để tạo test context tập trung vào router mà không khởi động toàn bộ Boot. Điều đó phù hợp cho unit-style routing tests nhưng không thay thế kiểm thử auto-configuration, codecs, filters và embedded HTTP server trong môi trường thật.

## 10. Thứ tự khai báo route và độ cụ thể của RequestPredicate

Functional routing thường hoạt động theo thứ tự: thử route đầu, nếu không match thì thử route sau. Vì vậy, **đặt route cụ thể trước route động hoặc rộng hơn**.

Ví dụ có nguy cơ:

~~~java
// Ví dụ thứ tự dễ gây nhầm:
return RouterFunctions.route()
        .GET("/api/items/{id}", handler::find)
        .GET("/api/items/featured", handler::featured)
        .build();
~~~

GET /api/items/featured có thể bị route /{id} nhận trước rồi chuyển featured thành path variable id, khiến route sau không được chọn.

Cách viết rõ ràng:

~~~java
return RouterFunctions.route()
        .GET("/api/items/featured", handler::featured)
        .GET("/api/items/{id}", handler::find)
        .build();
~~~

Đây là đoạn minh họa cấu trúc dùng trong từng stack; loại RouterFunctions/ServerResponse nhập vào phải đúng với WebMvc.fn hoặc WebFlux.fn của dự án.

Những điều cần nhớ:

- Route được kết hợp bởi and(), andOther(), add() hoặc builder có thứ tự ưu tiên trong quá trình match.
- Khi có nhiều RouterFunction beans, hệ thống có thể tổng hợp chúng theo order. Nếu có URL overlap, cần kiểm thử và khai báo thứ tự có chủ đích.
- Annotation-based @RequestMapping chọn handler theo cơ chế điều kiện và mức độ cụ thể của annotation mapping; **không nên bê nguyên quy tắc đó sang functional router**.
- Đường dẫn có context path, servlet mapping, trailing slash hoặc encoded character có thể ảnh hưởng matching; test bằng HTTP request tương ứng.
- Dùng HTTP method và media type predicates để giảm nhầm lẫn giữa GET/POST và JSON/text.

Một lỗi logic là đặt catch-all route /** trước các route con. Nó có thể nuốt cả các request lẽ ra phải xử lý bởi handler cụ thể hơn.

## 11. Nested routes: chia sẻ tiền tố đường dẫn

Khi nhiều endpoint cùng bắt đầu bằng /api/items, có thể nhóm chúng bằng nested routing để tránh viết lặp tiền tố:

~~~java
// Cấu trúc sử dụng cùng cú pháp builder ở WebMvc.fn và WebFlux.fn,
// với import RouterFunctions phù hợp stack.
return RouterFunctions.route()
        .path("/api/items", builder -> builder
                .GET("/featured", handler::featured)
                .GET("/{id}", handler::find)
                .POST(handler::create))
        .build();
~~~

Ví dụ trên minh họa ý tưởng nested path; với POST không ghi path con, route được map tại đường dẫn gốc của group theo DSL. Khi cần tránh mọi khác biệt DSL/phiên bản, cách viết explicit .POST("/api/items", ...) ở phần code chạy đầy đủ sẽ dễ kiểm chứng hơn.

Ngoài path, builder hỗ trợ thêm RequestPredicate như accept(APPLICATION_JSON) hoặc contentType(APPLICATION_JSON), có thể kết hợp trong nest() hoặc trong từng route. Hãy đặt predicate ở phạm vi nhỏ đủ để không vô tình từ chối endpoint vốn chấp nhận nội dung khác.

## 12. Functional filters: xử lý chung quanh handler

Functional endpoints hỗ trợ filter gắn với router. Đây là khái niệm khác với Servlet Filter hoặc reactive WebFilter:

- **HandlerFilterFunction của WebMvc.fn** nhận request và next handler, xử lý theo hợp đồng đồng bộ.
- **HandlerFilterFunction của WebFlux.fn** nhận request và next handler, trả Mono<ServerResponse>.
- **Servlet Filter** chạy ở lớp Servlet filter chain, có thể ảnh hưởng tới nhiều loại request ngoài functional routes.
- **WebFilter** xử lý cross-cutting ở reactive pipeline, bao gồm nhiều handler types.

Ví dụ tư duy với MVC.fn:

~~~java
RouterFunctions.route()
        .GET("/api/ping", request ->
                ServerResponse.ok().body("pong"))
        .filter((request, next) -> {
            // Có thể đọc request metadata hoặc ghi log.
            return next.handle(request);
        })
        .build();
~~~

Ví dụ tương ứng với WebFlux.fn:

~~~java
RouterFunctions.route()
        .GET("/api/ping", request ->
                ServerResponse.ok().bodyValue("pong"))
        .filter((request, next) -> {
            // Không block reactive event-loop.
            return next.handle(request);
        })
        .build();
~~~

Hai đoạn dành cho hai dự án riêng; chúng không bao gồm import vì minh họa sự khác nhau của body() và bodyValue(). Nếu filter cần đo thời gian completion, với WebFlux nên đặt logic vào các operator reactive như doFinally thay vì chỉ đo khoảng thời gian tạo Mono; Mono được subscribe và hoàn tất sau đó.

Lưu ý bảo mật: dùng Spring Security tương ứng với Servlet hay reactive stack để quản lý authentication/authorization. Không coi việc kiểm tra một header tự tạo bên trong functional filter là giải pháp bảo mật thay thế SecurityFilterChain/SecurityWebFilterChain.

## 13. Khi functional routes và annotated controllers cùng tồn tại

Spring cho phép kết hợp functional routing và annotation-based controller **trong cùng một web stack**:

- WebMvc.fn với @RestController của Spring MVC.
- WebFlux.fn với @RestController của Spring WebFlux.

Ví dụ một module dùng @RestController cho API legacy, module khác thêm functional RouterFunction cho API mới. Cách phối hợp này phù hợp cho migration từng phần hoặc nhóm route không cần annotation.

Tuy nhiên:

1. Không đăng ký trùng GET /api/items/{id} ở cả @GetMapping lẫn RouterFunction trong cùng ứng dụng mà không có chủ đích.
2. Đừng giả định thứ tự controller mapping và RouterFunctionMapping được xác định chỉ bởi thứ tự file Java.
3. Một filter gắn trên RouterFunction thường không tác động tới annotation-based controller; muốn áp dụng chính sách toàn bộ HTTP traffic, dùng filter của web stack hoặc cấu hình framework phù hợp.
4. WebMvcConfigurer chỉ tùy chỉnh MVC, WebFluxConfigurer chỉ tùy chỉnh WebFlux; việc bật cả hai không có nghĩa một application xử lý hai mô hình cùng lúc.
5. Những behavior chung như JSON serialization có thể được Boot cung cấp trong cả hai stack, nhưng đó là hai hệ thống message conversion khác nhau: HttpMessageConverter cho MVC và HttpMessageReader/Writer cho WebFlux.

Hãy tổ chức route theo module, đặt convention URL rõ ràng và viết regression tests cho cả hai loại handler trước khi thay đổi thứ tự cấu hình.

## 14. Request body và response body: điểm khác biệt lớn nhất trong code

### MVC.fn

~~~java
// Đồng bộ, trong handler MVC.fn
Map<?, ?> input = request.body(Map.class);
return ServerResponse.ok().body(
        Map.of("received", input.get("name")));
~~~

body(Class) dùng cơ chế đọc request đồng bộ của Servlet và HTTP message converter phù hợp. Nên tạo DTO riêng, kiểm tra null, parse errors và validation trong ứng dụng thật. Mẫu Map ở đây chỉ minh họa API.

### WebFlux.fn

~~~java
// Reactive, trong handler WebFlux.fn
return request.bodyToMono(Map.class)
        .flatMap(input -> ServerResponse.ok()
                .bodyValue(Map.of(
                        "received", input.get("name"))));
~~~

Không gọi block() để lấy Map rồi trả ServerResponse đồng bộ từ WebFlux.fn. Trường hợp body rỗng tạo Mono.empty có thể làm thiếu response; hãy xác định policy như switchIfEmpty hoặc defaultIfEmpty.

Với stream phản hồi nhiều phần tử trong WebFlux.fn, có thể sử dụng:

~~~java
Flux<Item> items = reactiveService.findAll();
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(items, Item.class);
~~~

Đoạn trên chỉ minh họa cách trả Publisher; nó cần Item và reactiveService do ứng dụng định nghĩa. NDJSON hoặc SSE có semantics khác một JSON array được buffer; cần chọn MediaType phù hợp, kiểm thử backpressure và xử lý hủy subscription.

WebMvc.fn cũng có thể phục vụ response dài hoặc streaming thông qua cơ chế được Servlet stack hỗ trợ, nhưng việc có streaming không tự biến request handler thành reactive và không nên giả định có cùng hành vi backpressure với WebFlux.

## 15. Blocking, concurrency và backpressure

Đây là điểm phân biệt quan trọng khi chọn giữa WebMvc.fn và WebFlux.fn.

**WebMvc.fn** hoạt động trên Spring MVC và Servlet infrastructure. Handler đồng bộ có thể gọi JDBC hoặc thư viện blocking theo cách thông thường. Tải cao vẫn cần sizing thread pool, connection pool, timeout và tránh giữ request thread quá lâu. Các cấu hình sử dụng virtual threads nếu có có thể làm mô hình worker thay đổi, nhưng HandlerFunction cơ bản vẫn trả ServerResponse trực tiếp.

**WebFlux.fn** được thiết kế cho reactive processing. Với Reactor Netty thông thường, event-loop threads nên tránh bị chặn bởi Thread.sleep, JDBC đồng bộ hoặc filesystem I/O chậm. Nếu không có reactive driver, có thể cô lập tác vụ blocking trên scheduler thích hợp như boundedElastic, nhưng phải kiểm soát concurrency và không biến mọi thao tác thành pseudo-reactive.

Ví dụ minh họa cách cô lập một API blocking trong reactive application:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> blockingLegacyService.load())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là đoạn minh họa cần Result, blockingLegacyService và Reactor Schedulers import phù hợp. Không phải một HTTP handler đầy đủ. Cần đảm bảo service có timeout, thread pool và resource lifecycle đúng. Chuyển thread không làm thư viện blocking thành non-blocking.

Backpressure xuất hiện khi downstream phát tín hiệu nhu cầu cho Publisher. Không nên hiểu nó như cam kết mọi hệ thống phụ thuộc (database, proxy, browser) tự động chấp nhận tốc độ vô hạn hoặc luôn được kiểm soát. Kiểm thử với response lớn, client ngắt kết nối và các luồng phụ thuộc.

**Chọn WebMvc.fn không hề là sai** khi nghiệp vụ chủ yếu dùng JDBC hoặc SDK blocking và hệ thống đã vận hành tốt trên Servlet. WebFlux.fn có lợi khi toàn bộ chuỗi I/O có thể khai thác mô hình reactive hợp lý, nhưng complexity cao hơn và phải cẩn trọng với blocking operations.

## 16. Bảo mật, CORS và lỗi HTTP

Các functional routes nằm trong cùng hệ thống security của stack mà chúng được đăng ký:

| Nhu cầu | MVC.fn | WebFlux.fn |
|---|---|---|
| Authentication/authorization | Servlet Spring Security SecurityFilterChain | Reactive Spring Security SecurityWebFilterChain |
| Common filter layer | jakarta.servlet.Filter / OncePerRequestFilter | WebFilter |
| CORS framework config | WebMvcConfigurer hoặc filter/security CORS config | WebFluxConfigurer hoặc CorsWebFilter/security CORS config |
| Handler-level functional filter | HandlerFilterFunction của servlet package | HandlerFilterFunction của reactive package |
| Error handling | MVC exception resolvers, error handling | WebExceptionHandler/ErrorWebExceptionHandler và reactive error processing |

Không đặt API bí mật dưới /api rồi nghĩ router predicate tự kiểm soát quyền. Router quyết định handler nào xử lý URL; security quyết định user/client nào được phép truy cập.

Đối với lỗi HTTP, cả hai ServerResponse APIs đều có builder cho những status phổ biến: ok(), badRequest(), notFound() và status(...). Tuy nhiên, cách propagate exception khác nhau:

- MVC.fn handler có thể ném exception đồng bộ; xử lý exception tuân theo MVC infrastructure và error resolvers phù hợp.
- WebFlux.fn handler có thể trả Mono.error(exception) hoặc publisher thất bại; lỗi được xử lý trong reactive error pipeline.
- Response đã commit body/headers thì không phải mọi lỗi xảy ra sau đó đều có thể đổi sang JSON 500. Với stream dài, client có thể chỉ nhận được connection close hoặc stream error.

**Tách lỗi nghiệp vụ thành status có ý nghĩa:** invalid input -> 400, không tìm thấy -> 404, tạo thành công -> 201. Tuy nhiên cần thiết kế error body thống nhất, validation và observability cho từng stack. Không coi mọi exception mặc định đều được chuyển thành response có format đẹp như ví dụ.

## 17. Định tuyến theo HTTP method, Content-Type và Accept

Route thường có ít nhất một HTTP method và path. Có thể bổ sung điều kiện media type:

- RequestPredicates.accept(MediaType.APPLICATION_JSON): kiểm tra kiểu response mà client chấp nhận qua Accept.
- RequestPredicates.contentType(MediaType.APPLICATION_JSON): kiểm tra kiểu nội dung request qua Content-Type.
- RequestPredicates.headers(...) hoặc predicate tự tạo: áp dụng điều kiện header khi cần.
- RequestPredicates.queryParam(...): áp dụng điều kiện query parameter trong các API hỗ trợ.

Với GET /api/items/42, nếu route yêu cầu Accept: application/json nhưng client đặt Accept: text/plain, route có thể không match. Kết quả cuối còn tùy các routes và error handlers khác, nên test thay vì chỉ đoán status.

Với POST /api/items, thiếu Content-Type: application/json có thể khiến route không match. Việc đọc body và validate sau khi match vẫn là trách nhiệm của handler. Không dùng Content-Type predicate thay cho kiểm tra JSON schema hoặc Bean Validation.

Ví dụ một endpoint hỗ trợ nhiều loại response cần định nghĩa rõ chiến lược negotiation. Nếu nhiều route có cùng method/path nhưng khác Accept, đặt route cụ thể đúng thứ tự và test từ browser, curl cùng các client thực tế.

## 18. Tổ chức RouterFunction theo module

Một dự án lớn có thể có các RouterFunction beans riêng cho từng module như catalog, orders, health. Cách này giúp package Java phản ánh nhóm URL, nhưng cần kiểm soát order.

Các cách tổ chức:

1. Một RouterFunction builder cho từng nhóm API, giữ route cụ thể trước route tổng quát.
2. Ghép RouterFunctions bằng andOther hoặc builder.add nếu muốn kiểm soát thứ tự trong một bean.
3. Nếu để nhiều beans, khai báo và kiểm chứng thứ tự bằng @Order hoặc Ordered khi cần.
4. Dùng nested route và shared RequestPredicates cho prefix hoặc media type chung.
5. Đặt handler trong class riêng để tách orchestration khỏi routing declaration.

Ví dụ cấu trúc:

~~~text
catalog/
    CatalogRoutes.java
    CatalogHandler.java
orders/
    OrderRoutes.java
    OrderHandler.java
shared/
    HttpErrorResponses.java
~~~

Không gom tất cả business logic vào lambda dài bên trong @Bean router. Điều đó làm khó mock dependency, viết test và phân tích lỗi.

Nếu có overlapping path giữa các module, đặt convention URL đủ rõ hoặc thêm tests kiểm tra request được điều hướng đến handler mong đợi.

## 19. Những lỗi thường gặp khi chuyển giữa WebMvc.fn và WebFlux.fn

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| IDE import sai ServerResponse | Hai stack có class trùng tên nhưng package khác | Kiểm tra org.springframework.web.servlet.function và org.springframework.web.reactive.function.server |
| MVC handler trả Mono<ServerResponse> | Nhầm hợp đồng HandlerFunction | MVC.fn trả ServerResponse trực tiếp; WebFlux.fn trả Mono<ServerResponse> |
| Gọi bodyValue() trên MVC ServerResponse builder | Dùng API reactive ở MVC | MVC.fn thường dùng body(value) |
| Gọi request.body(Map.class) trong WebFlux.fn | Dùng API đồng bộ của MVC | WebFlux.fn dùng bodyToMono(Map.class) |
| Route /{id} nuốt route /featured | Route động đặt trước route cụ thể | Đặt /featured trước /{id} |
| @RestController và functional routes cùng URL | Duplicate handler paths | Tránh trùng method/path, kiểm tra HandlerMapping order |
| Cả starter-web và starter-webflux nhưng ứng dụng không reactive | Boot thường chọn MVC khi có cả hai | Chọn starter rõ ràng, kiểm tra web application type |
| Blocking JDBC trong reactive handler | Chặn event-loop hoặc thread không phù hợp | Dùng reactive I/O hoặc cô lập blocking với scheduler phù hợp |
| Mono.empty không tạo response mong đợi | Handler không phát ServerResponse | Xác định fallback bằng switchIfEmpty hoặc error handling |
| Filter bảo mật gắn router không bao phủ endpoint khác | Filter phạm vi functional router | Dùng Spring Security FilterChain/WebFilter ở đúng stack |
| Mặc định static resources hoặc codecs bị mất | Tùy chỉnh quá mức bằng @EnableWebMvc/@EnableWebFlux | Giữ Boot auto-configuration khi không cần full control |
| MockMvc test dùng với reactive-only app | Sai test stack | Dùng WebTestClient cho WebFlux |
| WebTestClient trả 404 dù @Bean tồn tại | Sai web type, route path/predicate hoặc bean không được scan | Kiểm tra startup report và unit/integration tests |

Một lỗi đáng chú ý nữa: cố dùng WebFlux.fn trong ứng dụng MVC chỉ vì đã thêm dependency spring-webflux để sử dụng WebClient. Spring WebFlux library có trên classpath không đồng nghĩa reactive RouterFunction beans được đăng ký trong DispatcherServlet của MVC application.

## 20. Checklist lựa chọn mô hình cho dự án

Trước khi quyết định giữa WebMvc.fn và WebFlux.fn, hãy trả lời:

1. Ứng dụng thực tế chạy Servlet MVC hay reactive WebFlux?
2. Dự án có sử dụng nhiều SDK blocking hoặc JDBC truyền thống không?
3. HTTP clients và data access đã hỗ trợ non-blocking hay chưa?
4. Route hiện tại đã dùng @RestController, có cần functional style cho một phần API không?
5. Có thể chia module rõ và kiểm soát route order không?
6. Dữ liệu request/response có cần streaming, SSE hoặc backpressure không?
7. Các security filters/CORS/error handlers có được thiết kế đúng stack không?
8. Cần MockMvc hay WebTestClient để bảo đảm regression coverage?
9. Có đủ observability/timeout/retry để hỗ trợ stack được chọn không?
10. Mỗi method/path/media type combination có test xác nhận handler nào nhận request không?

**Chọn WebMvc.fn** nếu ứng dụng đang là Spring MVC và chỉ muốn định nghĩa route bằng functional style; không cần đổi toàn bộ hệ thống sang reactive. **Chọn WebFlux.fn** nếu ứng dụng đã chủ động dùng reactive stack và muốn định tuyến bằng hàm cùng Publisher-based processing. Với cả hai, nguyên tắc cấu trúc route và nội dung API có thể gần giống, nhưng dependency, import, HandlerFunction contract và kiểm thử phải tương ứng với stack.

## 21. Tài liệu chính thức

- [Spring Framework 6.2 – WebMvc.fn functional endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html)
- [Spring Framework 6.2 – WebFlux.fn functional endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 – Annotated controllers MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller.html)
- [Spring Framework 6.2 – WebFlux configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Boot 3.5 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)

**Tóm lại:** WebMvc.fn và WebFlux.fn đều khai báo RouterFunction và HandlerFunction, nhưng WebMvc.fn thuộc Servlet MVC và trả ServerResponse đồng bộ, còn WebFlux.fn thuộc reactive WebFlux và trả Mono<ServerResponse>. Phân biệt đúng package, web stack, cách đọc body, execution model và test framework là chìa khóa để xây functional endpoints chính xác, dễ bảo trì.