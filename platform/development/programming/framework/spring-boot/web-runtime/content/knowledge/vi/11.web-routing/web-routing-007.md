# Ghép route, nhóm đường dẫn và thứ tự lựa chọn handler trong Spring Boot

Trong Spring Boot web runtime, **routing** quyết định HTTP request nào được chuyển đến handler nào. Một route có thể phụ thuộc vào URL path, HTTP method, query parameter, header, Content-Type và Accept. Khi dự án có hàng chục controller hay nhiều functional router, cần hiểu ba việc: **ghép route**, **nhóm path**, và **thứ tự chọn handler**.

**Phân biệt nền tảng:**
- Với **annotated controller** (`@RequestMapping`, `@GetMapping`), Spring MVC/WebFlux so sánh các mapping phù hợp và ưu tiên điều kiện/pattern cụ thể hơn. Không lấy thứ tự method trong source file làm quyền ưu tiên.
- Với **functional routing** (`RouterFunction`), các nhánh kết hợp thường được xét **theo thứ tự**; nhánh khớp đầu tiên thắng. Nên đặt literal/specific route trước variable/catch-all route.
- Ở cấp cao hơn, `DispatcherServlet` (MVC) hoặc `DispatcherHandler` (WebFlux) hỏi các `HandlerMapping` theo thứ tự `order`. Một HandlerMapping tìm thấy handler trước có thể ngăn cơ chế mapping khác được xét tiếp.

## 1. Một HTTP route gồm những điều kiện nào?

Ví dụ một request:

~~~http
GET /api/v1/products/42?detail=true HTTP/1.1
Host: example.test
Accept: application/json
~~~

Các thành phần được dùng khi matching:

| Thuộc tính | Giá trị ví dụ | Mục đích |
|---|---|---|
| Path | `/api/v1/products/42` | Chọn nhóm và endpoint |
| HTTP method | GET | Phân biệt GET/POST/PUT/DELETE trên cùng path |
| Query parameter | `detail=true` | Có thể tham gia predicate `params` |
| Header | Accept: application/json | Điều kiện `produces`, content negotiation |
| Content-Type | Ví dụ application/json khi có body | Điều kiện `consumes` và chọn body converter |

Query string không phải là phần của path pattern; `/products?sort=name` và `/products?sort=price` có cùng path `/products` nhưng có thể được phân biệt bằng điều kiện `params`.

Route được chọn là kết quả của **tổng hợp điều kiện**, không chỉ so sánh một chuỗi đường dẫn.

## 2. Đường đi request tới HandlerMapping

Với Spring MVC Servlet stack:

~~~text
Client
 -> Servlet container (Tomcat / Jetty / Undertow)
 -> Servlet FilterChain (có thể gồm Spring Security)
 -> DispatcherServlet
 -> HandlerMapping theo order
 -> HandlerAdapter
 -> Controller hoặc HandlerFunction
 -> HTTP response
~~~

Với Spring WebFlux reactive stack, framework thường sử dụng `DispatcherHandler` và các reactive `HandlerMapping` / `HandlerAdapter`; trên Reactor Netty, không có Servlet FilterChain theo cách triển khai Servlet thông thường.

Một số mapping strategy trong MVC:

- `RequestMappingHandlerMapping`: annotated controllers.
- `RouterFunctionMapping`: functional routes của Spring MVC.
- Resource handler mappings: phục vụ tài nguyên tĩnh theo cấu hình.
- HandlerMapping khác do framework/ứng dụng cung cấp.

Spring dùng `HandlerMapping` trả handler đầu tiên theo thứ tự đã cấu hình. Vì vậy, **độ đặc hiệu của annotated route không phải phép so sánh toàn cục giữa tất cả RouterFunction và controller khác nhau**. Cần phân biệt thứ tự HandlerMapping với thứ tự nhánh bên trong một functional router.

## 3. Ghép URL: class-level và method-level @RequestMapping

Spring MVC cho phép nhóm endpoint bằng một prefix ở controller:

~~~java
@RestController
@RequestMapping("/api/v1/users")
class UserController {

    @GetMapping
    String listUsers() {
        return "list";
    }

    @GetMapping("/{id}")
    String byId(@PathVariable String id) {
        return "user:" + id;
    }

    @PostMapping
    String createUser() {
        return "created";
    }
}
~~~

Đây là fragment cần các import và dự án Spring MVC. Các URL:

| Request | Method |
|---|---|
| GET `/api/v1/users` | `listUsers()` |
| GET `/api/v1/users/9` | `byId("9")` |
| POST `/api/v1/users` | `createUser()` |

`@RequestMapping` trên class đóng vai trò prefix/điều kiện chung; `@GetMapping` và `@PostMapping` trên method bổ sung đường dẫn con và HTTP method. Một method cũng có thể khai báo nhiều path bằng mảng đường dẫn; cần bảo đảm các alias đó có cùng ngữ nghĩa.

### 3.1. Context path không phải prefix của controller

Nếu `application.yml` có:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /shop
~~~

thì client gọi `GET /shop/api/v1/users`, trong khi controller vẫn khai báo `@RequestMapping("/api/v1/users")`. Không chép `/shop` vào annotation, vì đó là context path ở tầng Servlet container.

`spring.mvc.servlet.path`, nếu được cấu hình, còn là path mapping của DispatcherServlet và khác với context path. Reverse proxy/ingress cũng có thể rewrite URL; phải xem đường dẫn thực tế được chuyển đến ứng dụng, không chỉ URL client nhìn thấy.

## 4. Điều kiện method, params, headers, consumes và produces

Nhiều mapping có thể cùng URL nhưng khác điều kiện:

~~~java
@GetMapping(path = "/reports", params = "mode=short",
            produces = "text/plain")
String shortReport() {
    return "short";
}

@GetMapping(path = "/reports", params = "mode=full",
            produces = "text/plain")
String fullReport() {
    return "full";
}
~~~

Đây là fragment trong controller; hai endpoint có cùng URL path `/reports`, nhưng khác `params`. Request `GET /reports?mode=short` chọn handler thứ nhất; `GET /reports?mode=full` chọn handler thứ hai.

Với body:

~~~java
@PostMapping(path = "/reports",
             consumes = "application/json",
             produces = "application/json")
ResponseEntity<ReportDto> create(
        @RequestBody CreateReportDto input) {
    // Service logic và return response ...
}
~~~

Đây là fragment minh họa, thiếu domain types/service nên không phải class chạy độc lập. `consumes` đối chiếu Content-Type của request body; `produces` đối chiếu khả năng trả response và Accept của client.

**Chú ý:** class-level và method-level annotation có cơ chế kết hợp điều kiện riêng; `consumes`/`produces` ở method có thể override điều kiện media type ở class. Đừng giả định mọi thuộc tính được nối/giao nhau như hai chuỗi path.

Khi chọn handler thất bại, thông báo có thể là 404, 405, 406 hoặc 415 tùy loại điều kiện không thỏa và mapping/exception handler khác. Không chẩn đoán tất cả là “sai URL”.

## 5. Annotated controllers chọn route cụ thể hơn

Giả sử hai mapping:

~~~java
@GetMapping("/products/new")
String newProduct() {
    return "new";
}

@GetMapping("/products/{id}")
String product(@PathVariable String id) {
    return "id:" + id;
}
~~~

Request `GET /products/new` phù hợp cả literal route và variable pattern. Spring annotated mapping ưu tiên `/products/new` vì cụ thể hơn `/products/{id}`. Request `GET /products/42` chọn handler với `{id}`.

**Thứ tự khai báo hai method không phải cách chọn ưu tiên.** Spring dùng thuật toán so sánh request mappings dựa trên path specificity và các điều kiện khác. Với `PathPatternParser`, pattern literal thường cụ thể hơn variable, trong khi catch-all `/**` rộng hơn nhiều.

Một cách hạn chế path variable:

~~~java
@GetMapping("/orders/{id:[0-9]+}")
String order(@PathVariable String id) {
    return "order:" + id;
}
~~~

Pattern nhận `/orders/123` nhưng không nhận `/orders/new`. Nếu ID là UUID hoặc mã có chữ, đừng dùng regex chỉ dành cho chữ số. Với `PathPatternParser`, catch-all như `/**` hoặc `/{*path}` có những quy tắc vị trí, thường phải nằm cuối pattern.

### 5.1. Ambiguous mapping không được chữa bằng đổi thứ tự

Ví dụ không nên khai báo trong cùng controller:

~~~java
@GetMapping("/items/{id}")
String byId(@PathVariable String id) {
    return "id";
}

@GetMapping("/items/{code}")
String byCode(@PathVariable String code) {
    return "code";
}
~~~

Tên biến `id` và `code` không tạo ra hai route có ngữ nghĩa matching khác nhau; chúng tương đương về cấu trúc. Tùy mapping còn lại, framework có thể phát hiện xung đột khi đăng ký hoặc ở runtime. Cách xử lý là thay đổi thiết kế:

~~~text
GET /items/by-id/{id}
GET /items/by-code/{code}
~~~

Các route có điều kiện khác nhau một cách rõ ràng dễ hiểu hơn việc trông chờ method nào nằm trước trong file.

## 6. Functional routing và RequestPredicate

Spring cũng hỗ trợ lập trình route dưới dạng function. Những thành phần chính:

- `RequestPredicate`: xác định một request có khớp điều kiện không.
- `HandlerFunction<ServerResponse>`: xử lý request thành response.
- `RouterFunction<ServerResponse>`: kết hợp predicate và handler.
- `RouterFunctions.route(...)` hoặc builder `route()`: định nghĩa route.
- `RouterFunctions.nest(...)` hoặc builder `path(...)`: tạo nhóm route con.
- `and(...)` / `andRoute(...)`: ghép các router hoặc các nhánh.

**Cần dùng đúng package:** MVC Servlet dùng `org.springframework.web.servlet.function.*`; WebFlux reactive dùng `org.springframework.web.reactive.function.server.*`. Mô hình tương tự nhưng không được hoán đổi type của hai stack.

Fragment Spring MVC functional routing:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/status", request ->
                        ServerResponse.ok().body("up"))
                .GET("/api/version", request ->
                        ServerResponse.ok().body("v1"))
                .build();
~~~

Các handler ở đây trả `ServerResponse` của Servlet functional API, không phải `Mono<ServerResponse>`.

## 7. Nhóm đường dẫn bằng path hoặc nest

Một nhóm API catalog có các URL:

~~~text
GET /api/v1/catalog/featured
GET /api/v1/catalog/{sku}
~~~

Thay vì lặp lại tiền tố ở từng route:

~~~java
RouterFunction<ServerResponse> catalogRoutes =
        RouterFunctions.route()
                .path("/api/v1/catalog", catalog -> {
                    catalog.GET("/featured", request ->
                            ServerResponse.ok().body("featured"));
                    catalog.GET("/{sku}", request ->
                            ServerResponse.ok().body(
                                    "sku:" + request.pathVariable("sku")));
                })
                .build();
~~~

Đây là fragment Spring MVC functional route. Builder `path(...)` áp dụng prefix chung cho nhóm; các route con chỉ khai báo phần đường dẫn còn lại. `RouterFunctions.nest(...)` cũng dùng để nhóm các RequestPredicate và router khác nhau; nesting không đơn thuần là phép nối string mà còn có thể phối hợp predicate phù hợp.

Nhóm route thường có giá trị khi:

- Phân tách API theo module: users, orders, catalog.
- Chia version: `/api/v1`, `/api/v2`.
- Gom endpoint quản trị: `/internal` với security rule riêng.
- Cấu trúc router được tái sử dụng, kết hợp bằng `and`.
- Chỉ muốn áp dụng một điều kiện path/header chung cho một nhóm.

Nesting không tự cung cấp authentication/authorization. Đường dẫn nhóm là dấu hiệu tổ chức, còn bảo mật phải được cấu hình bằng Spring Security phù hợp.

## 8. Thứ tự trong functional route: first match

Đây là khác biệt rất quan trọng so với annotated mapping. Trong functional router, các nhánh được xét theo thứ tự kết hợp. Nếu một nhánh tổng quát đứng trước, request có thể bị nó bắt trước khi đến nhánh cụ thể.

**Ví dụ sai:**

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/products/{id}", req ->
                        ServerResponse.ok().body("id:" + req.pathVariable("id")))
                .GET("/products/new", req ->
                        ServerResponse.ok().body("new-product"))
                .build();
~~~

`GET /products/new` có thể khớp `/{id}` ở nhánh đầu và trả `id:new`. Để tránh:

**Ví dụ đúng:**

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/products/new", req ->
                        ServerResponse.ok().body("new-product"))
                .GET("/products/{id}", req ->
                        ServerResponse.ok().body("id:" + req.pathVariable("id")))
                .build();
~~~

Quy tắc thực hành:

1. Đặt exact/literal route trước các pattern có biến.
2. Đặt predicate hẹp về header, param và media type trước predicate rộng khi có giao nhau.
3. Đặt catch-all `/**` cuối cùng và chỉ trong phạm vi thực sự cần.
4. Khi ghép nhiều router bằng `and`, phải kiểm tra thứ tự của các thành phần đã kết hợp.
5. Nếu cần bảo đảm quyền ưu tiên giữa nhiều handler types, xem `HandlerMapping order` ở tầng cao hơn; không nhầm first-match **bên trong router** với thứ tự của toàn Spring MVC.

## 9. Ví dụ Java 17+ chạy được: Spring MVC controller và functional route

Ví dụ dùng Spring Boot 3.x, `spring-boot-starter-web` và embedded Tomcat mặc định. Phần controller và functional routes dùng **hai namespace khác nhau** để tránh xung đột.

Trong `build.gradle` của dự án có Spring Boot plugin và quản lý dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tệp **src/main/java/demo/routing/RoutingApplication.java**:

~~~java
package demo.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/v1/users")
class UserController {

    @GetMapping("/me")
    String me() {
        return "current-user";
    }

    @GetMapping("/{id}")
    String byId(@PathVariable String id) {
        return "user:" + id;
    }
}

@Configuration(proxyBeanMethods = false)
class CatalogConfiguration {

    @Bean
    RouterFunction<ServerResponse> catalogRoutes() {
        return RouterFunctions.route()
                .path("/api/v1/catalog", catalog -> {
                    catalog.GET("/featured", request ->
                            ServerResponse.ok().body("featured"));
                    catalog.GET("/{sku}", request ->
                            ServerResponse.ok().body(
                                    "sku:" + request.pathVariable("sku")));
                })
                .build();
    }
}
~~~

Lớp public khớp tên file. Hai class còn lại là package-private và nằm cùng package nên được `@SpringBootApplication` quét.

Chạy dự án qua Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows có thể dùng `gradlew.bat bootRun`. Khi ứng dụng chạy ở cổng mặc định 8080, không có Spring Security hoặc filter chặn, thử:

~~~bash
curl -s http://localhost:8080/api/v1/users/me
curl -s http://localhost:8080/api/v1/users/42
curl -s http://localhost:8080/api/v1/catalog/featured
curl -s http://localhost:8080/api/v1/catalog/A7
~~~

Response body của **từng lệnh**:

~~~text
current-user
user:42
featured
sku:A7
~~~

Bốn dòng trên được trình bày riêng để dễ đọc; các response body không nhất thiết chứa newline.

**Vì sao kết quả đúng?** Với controller, đường dẫn literal `/me` thắng variable `/{id}` nhờ độ đặc hiệu annotated mapping. Với functional router, `/featured` đứng trước `/{sku}`, nên request catalog featured vào handler cụ thể; request có SKU tùy ý vào handler phía sau.

## 10. Kiểm thử thứ tự chọn handler bằng MockMvc

Chỉ xác nhận bean router đã được tạo là chưa đủ. Nên kiểm tra trực tiếp những URL có nguy cơ chồng lấn. Thêm vào `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tệp **src/test/java/demo/routing/RoutingApplicationTest.java**:

~~~java
package demo.routing;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void annotationPicksLiteralRoute() throws Exception {
        mvc.perform(get("/api/v1/users/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("current-user"));

        mvc.perform(get("/api/v1/users/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("user:42"));
    }

    @Test
    void functionalRouterPicksFirstMatchingBranch() throws Exception {
        mvc.perform(get("/api/v1/catalog/featured"))
                .andExpect(status().isOk())
                .andExpect(content().string("featured"));

        mvc.perform(get("/api/v1/catalog/A7"))
                .andExpect(status().isOk())
                .andExpect(content().string("sku:A7"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

`MockMvc` kiểm thử MVC stack mà không mở socket HTTP thật. Với ví dụ có dependencies và cấu hình như trên, test xác minh cả literal/variable routing và functional ordering. Khi cần kiểm tra context path, reverse proxy hoặc Servlet container network behavior, dùng thêm integration test `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng HTTP client.

## 11. Thứ tự HandlerMapping và route chồng lấn giữa các kiểu

Một ứng dụng có thể dùng cả annotated controller, functional route và static resources. Khi đó có **hai cấp độ quyết định**:

**Cấp 1:** DispatcherServlet đi qua các HandlerMapping theo `order`, dùng handler đầu tiên tìm được.

**Cấp 2:** Trong từng strategy, framework đánh giá route:
- Annotated mapping chọn theo điều kiện và độ đặc hiệu.
- Functional router dùng cách ghép/nest và thứ tự nhánh.
- Static resource handler có quy tắc URL và resource resolution riêng.

Giả sử functional router có một fallback `/**`, và ứng dụng cũng có annotated controller `/api/users`. Nếu RouterFunctionMapping được xét trước và fallback khớp, handler của controller có thể không được gọi. Tình huống thực tế phụ thuộc effective HandlerMapping order; không suy đoán số order cố định cho mọi phiên bản/cấu hình.

**Đừng dùng `@Order` trên controller như giải pháp thay cho độ đặc hiệu của `@GetMapping`.** Khi muốn ưu tiên route, điều chỉnh pattern/conditions rõ ràng; nếu dùng functional router, tổ chức thứ tự của các nhánh và tránh path quá rộng.

## 12. WebFlux cũng có annotated và functional routing

WebFlux annotated controller có semantics gần với MVC về request mapping conditions và độ đặc hiệu:

~~~java
@RestController
@RequestMapping("/api/items")
class ReactiveItemController {

    @GetMapping("/featured")
    Mono<String> featured() {
        return Mono.just("featured");
    }

    @GetMapping("/{id}")
    Mono<String> item(@PathVariable String id) {
        return Mono.just("item:" + id);
    }
}
~~~

Đây là fragment, cần imports từ Spring WebFlux và Project Reactor. Reactive controller trả `Mono` và được điều phối bởi `DispatcherHandler`, không phải Servlet DispatcherServlet trong trường hợp WebFlux chạy trên Reactor Netty.

### Functional WebFlux example

Ở một dự án **khác**, chỉ sử dụng starter WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Tệp **src/main/java/demo/reactive/ReactiveRoutingApplication.java**:

~~~java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@SpringBootApplication
public class ReactiveRoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveRoutingApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> catalogRoutes() {
        return RouterFunctions.route()
                .path("/api/v1/catalog", b -> {
                    b.GET("/featured", request ->
                            ServerResponse.ok().bodyValue("featured"));
                    b.GET("/{sku}", request ->
                            ServerResponse.ok().bodyValue(
                                    "sku:" + request.pathVariable("sku")));
                })
                .build();
    }
}
~~~

Trong WebFlux, `ServerResponse.ok().bodyValue(...)` là reactive response builder, trả publisher `Mono<ServerResponse>` theo API tương ứng. Không cần gọi `block()` để chuyển thành Servlet response.

Khi ứng dụng chạy, `GET /api/v1/catalog/featured` trả `featured`, còn `GET /api/v1/catalog/X9` trả `sku:X9`. Route literal được đặt trước variable route để bảo vệ first-match.

**Không gộp ví dụ MVC và WebFlux vào cùng module mà giả định cả hai router cùng được đăng ký.** Nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trên classpath, Spring Boot thường ưu tiên Servlet MVC mặc định. Cần xác định web application type và server runtime thực tế.

## 13. Các trạng thái lỗi dễ bị hiểu sai

| HTTP status | Nguyên nhân thường gặp |
|---|---|
| 404 | Không tìm được path/handler phù hợp hoặc resource không tồn tại |
| 405 | Path có mapping nhưng HTTP method không được hỗ trợ |
| 406 | `Accept` không tương thích với response `produces` |
| 415 | `Content-Type` không tương thích với `consumes` hoặc body media type |
| 400 | Tham số không phù hợp, lỗi binding/validation/body |
| 401/403 | Authentication/authorization (thường xảy ra trước handler) |
| 500 | Lỗi không xử lý được hoặc handler/configuration bị lỗi |

Đây là những kết quả **điển hình**, không phải bảo đảm tuyệt đối khi có custom exception handler, filter và security.

Các câu hỏi debug nên theo thứ tự: client request thực sự là gì? Có proxy/context-path rewrite không? Request có bị filter/security chặn trước MVC không? HandlerMapping nào nhận request? Trong RouterFunction, nhánh nào khớp đầu tiên? Media type và request method có đúng không?

## 14. PathPatternParser, slash và catch-all

Các phiên bản Spring Framework hiện đại thường dùng `PathPatternParser` cho annotated mapping. So với quy tắc Ant matching ở một số dự án cũ, có khác biệt ở pattern hợp lệ, encoded path, trailing slash và wildcard.

Ví dụ:

- `/users/me` là path literal cụ thể.
- `/users/{id}` khớp một path segment.
- `/users/{id:[0-9]+}` chỉ nhận segment theo regex số.
- `/assets/**` là catch-all cho phần path còn lại theo cấu hình tương ứng.

Không giả định `/users` và `/users/` luôn match giống nhau, nhất là khi nâng phiên bản Spring. Tùy cấu hình, optional trailing slash matching có thể không được bật. Test cả dạng có/không có slash nếu client thực tế dùng cả hai.

Một số wildcard/catch-all trong PathPattern chỉ hợp lệ ở cuối pattern. Nếu route không được đăng ký hoặc matching thay đổi sau nâng Spring, cần kiểm tra strategy và cú pháp pattern thay vì chỉ sửa order.

## 15. Bảo mật và route groups

Đường dẫn nhóm `/internal/**` không tự làm endpoint an toàn. Spring Security có filter chain/authorization matcher riêng, có thể xử lý request **trước** DispatcherServlet hoặc reactive DispatcherHandler. Do đó:

- Không lấy “route này cụ thể hơn” làm chính sách authorization.
- Security matcher và route matcher có thể dùng cơ chế path khác nhau.
- Khi có reverse proxy/Servlet context path, phải xác nhận path mà security filter thực sự nhìn thấy.
- Functional catch-all không phải giải pháp xử lý request bị security chặn.
- Test các route nhạy cảm bằng request có và không có quyền.

Đặt phân quyền ở cơ chế security phù hợp; không chờ controller tự bảo vệ tất cả endpoint nếu filter đã hoặc nên xử lý trước.

## 16. Kiểm tra routes đã đăng ký

Nếu ứng dụng có Actuator, `/actuator/mappings` có thể giúp quan sát các mapping đã được Spring Boot nhận diện. Thêm dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Cấu hình expose endpoint trong môi trường kiểm thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,mappings
~~~

Sau khi chạy với management endpoint trên cổng ứng dụng:

~~~bash
curl -s http://localhost:8080/actuator/mappings
~~~

Response có thể gồm thông tin handler mappings, controllers và request predicates, tùy phiên bản Boot. Không khẳng định một cấu trúc JSON cố định. Vì endpoint này tiết lộ cấu trúc nội bộ, **giới hạn truy cập** trong production.

Có thể dùng logging của Spring MVC/WebFlux để kiểm tra request được ánh xạ vào handler nào. Không log token, Authorization header, cookie hoặc nội dung nhạy cảm chỉ để debug routing.

## 17. Lỗi thường gặp

**Lỗi 1 — Ghép prefix hai lần:** đã có `server.servlet.context-path=/shop` nhưng controller còn khai báo `/shop/api`. Kết quả client-visible path lặp prefix. Sửa ở đúng tầng.

**Lỗi 2 — Cho rằng thứ tự method controller quyết định handler:** annotated mapping có thuật toán so sánh, không phụ thuộc vị trí source. Viết pattern/conditions rõ ràng.

**Lỗi 3 — Functional variable route đứng trước literal:** `/{id}` nuốt `/new` hoặc `/featured`. Đặt literal trước.

**Lỗi 4 — Functional catch-all đứng đầu:** `/**` có thể chặn các nhánh cụ thể và thậm chí tác động handler khác tùy HandlerMapping order. Đưa fallback cuối và thu hẹp prefix.

**Lỗi 5 — Hai mapping khác tên path variable nhưng cùng cấu trúc:** `/{id}` và `/{code}` có thể gây ambiguity. Tách URL theo ý nghĩa hoặc thêm điều kiện khác.

**Lỗi 6 — Nhầm 405/406/415 với 404:** kiểm tra HTTP method, consumes, produces và client headers, không chỉ URL.

**Lỗi 7 — Nhầm MVC functional với WebFlux functional:** cùng tên `RouterFunction` nhưng package và response type khác. Kiểm tra stack/runtime.

**Lỗi 8 — Thêm cả starter-web và starter-webflux rồi tưởng server reactive:** Spring Boot thường ưu tiên MVC khi cả hai có mặt. Xác nhận kiểu web runtime.

**Lỗi 9 — Bảo mật dựa vào thứ tự route:** request có thể bị chặn trước handler; auth policy phải độc lập và được test.

**Lỗi 10 — Chỉ test một URL:** không phát hiện vấn đề khi literal/variable route giao nhau. Test các trường hợp chồng lấn cùng với method/media type và fallback.

## 18. Checklist triển khai

1. Xác định ứng dụng chạy Spring MVC/Servlet hay Spring WebFlux/Reactive.
2. Xác định URL mà ứng dụng nhận sau ingress, context path, servlet path hoặc base path.
3. Nhóm controller bằng class-level `@RequestMapping` và method-level mapping rõ ràng.
4. Với functional API, nhóm path bằng `path`/`nest` và ghép router bằng `and` theo thứ tự có chủ đích.
5. Đặt route literal và predicate cụ thể trước variable/catch-all trong functional routing.
6. Đừng dựa vào thứ tự source method với annotated mappings.
7. Kiểm tra đường dẫn `/{id}`, `/me`, regex và wildcard để tránh ambiguity.
8. Hiểu rõ khác biệt giữa **specificity của một mapping** và **HandlerMapping order**.
9. Test cả URL đúng, URL không tồn tại, method sai, media type không chấp nhận, authentication bị từ chối.
10. Dùng Actuator mappings/logging có kiểm soát để chẩn đoán handler được chọn.
11. Không trộn route MVC và WebFlux functional mà chưa xác định stack.
12. Chạy regression tests sau mỗi thay đổi module, version prefix hoặc fallback router.

**Kết luận:** Nhóm đường dẫn giúp quản lý route theo module và version; ghép route giúp giảm lặp điều kiện. Nhưng khi nhiều endpoint có thể khớp, cần phân biệt **annotated mapping specificity**, **functional router first-match** và **thứ tự HandlerMapping**. Thiết kế namespace rõ, giữ các route cụ thể trước route tổng quát trong functional router, và có test cho các đường dẫn chồng lấn sẽ giúp việc lựa chọn handler đúng, dự đoán được và dễ bảo trì.