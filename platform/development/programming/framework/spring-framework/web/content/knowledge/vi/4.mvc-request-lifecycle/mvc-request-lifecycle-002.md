# HandlerMapping: tìm thành phần xử lý phù hợp với yêu cầu trong Spring MVC

## 1. Mục tiêu và vị trí trong luồng MVC

Một HTTP request đi vào `DispatcherServlet` chưa tự biết controller method nào phải chạy. **`HandlerMapping`** là chiến lược giúp Spring MVC tìm **handler phù hợp với request hiện tại**, đồng thời cung cấp chuỗi interceptor liên quan. Mỗi loại `HandlerMapping` hiểu một kiểu khai báo route khác nhau: annotation, URL mapping thủ công, functional endpoint hoặc tài nguyên tĩnh.

Sau bài học, bạn có thể:

1. Giải thích đúng trách nhiệm của `HandlerMapping` trong `DispatcherServlet` và phân biệt với `HandlerAdapter`.
2. Hiểu `HandlerExecutionChain`, `HandlerMethod` và mối liên hệ với `HandlerInterceptor`.
3. Đọc và dự đoán endpoint nào được chọn từ `@RequestMapping`, `@GetMapping`, `@PostMapping` và các điều kiện path, HTTP method, params, headers, consumes, produces.
4. Hiểu quy tắc chọn mapping cụ thể hơn, thứ tự giữa các `HandlerMapping` và tình huống trùng/không tìm được handler.
5. Chạy ví dụ Spring MVC Java 17+, quan sát kết quả bằng HTTP request, kiểm tra route được đăng ký và gỡ lỗi 404/405/406/415.

**Phạm vi:** Spring MVC chạy trên Servlet stack (`spring-webmvc`), minh họa hành vi phổ biến của Spring Framework 6.x / Spring Boot 3.x. Trong Spring WebFlux có các lớp và pipeline dispatch reactive tương ứng nhưng không được dùng thay thế lẫn nhau.

## 2. `HandlerMapping` làm gì trong `DispatcherServlet`?

Hãy theo dõi một request:

```text
Client: GET /api/books/42
               |
          Servlet container
               |
         DispatcherServlet
               |
      [Lần lượt hỏi HandlerMapping]
               |
      HandlerExecutionChain
       + selected handler
       + 0..n interceptors
               |
        HandlerAdapter phù hợp
               |
      gọi controller method
               |
      xử lý giá trị trả về,
      ghi HTTP body / render view
               |
          HTTP response
```

`HandlerMapping` thực hiện việc **tra cứu**, không tự gọi business method. Tại runtime, `DispatcherServlet` duyệt các `HandlerMapping` đã được cấu hình theo thứ tự ưu tiên. Với mỗi mapping, nó gọi:

```java
HandlerExecutionChain getHandler(HttpServletRequest request)
        throws Exception;
```

Đây là **chữ ký khái niệm từ interface `org.springframework.web.servlet.HandlerMapping`**, không phải phương thức bạn thường tự gọi trong controller. Kết quả có hai dạng chính:

- Một `HandlerExecutionChain` chứa handler tìm thấy và các interceptor gắn với request.
- `null` nếu mapping cụ thể **không** nhận request đó, để dispatcher hỏi mapping tiếp theo.

Một handler có thể là `HandlerMethod` đại diện cho một phương thức của `@Controller`, hoặc là kiểu khác như `HttpRequestHandler`, `Controller` kiểu cũ, `HandlerFunction` của MVC functional endpoints. Vì handler có nhiều kiểu, `DispatcherServlet` chuyển kết quả cho **`HandlerAdapter` tương thích** để gọi handler.

**Phân biệt cốt lõi:**

| Thành phần | Câu hỏi mà nó giải quyết | Ví dụ |
| --- | --- | --- |
| `DispatcherServlet` | Ai điều phối toàn bộ HTTP request trong Spring MVC? | Front controller |
| `HandlerMapping` | Request này thuộc handler nào? | `RequestMappingHandlerMapping` |
| `HandlerExecutionChain` | Handler đã chọn và interceptor nào đi kèm? | `HandlerMethod` + một `HandlerInterceptor` |
| `HandlerAdapter` | Làm sao gọi đúng loại handler, resolve tham số và xử lý kết quả? | `RequestMappingHandlerAdapter` |
| `HttpMessageConverter` | Đọc/ghi request hoặc response body theo media type thế nào? | Chuyển Java object thành JSON |
| `ViewResolver` | Nếu kết quả là view name, tìm view để render thế nào? | Resolve template HTML |

Vì thế, lỗi “không tìm thấy handler” xảy ra ở giai đoạn trước khi business method được gọi; lỗi binding, JSON converter hay business exception có thể xảy ra ở các giai đoạn khác.

## 3. Các `HandlerMapping` phổ biến

### 3.1. `RequestMappingHandlerMapping`: mapping theo annotation

Đây là mapping quan trọng nhất với các REST controller dựa trên annotation. Khi application context khởi tạo, Spring phát hiện các handler method từ controller bean và đăng ký metadata về mapping; trong quá trình xử lý request, nó so sánh request với các điều kiện đã đăng ký.

Ví dụ một controller:

```java
package example.routes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/latest")
    public String latest() {
        return "latest book";
    }

    @GetMapping("/{id}")
    public String byId(@PathVariable String id) {
        return "book:" + id;
    }
}
```

`@RequestMapping("/api/books")` ở mức class kết hợp với `@GetMapping` ở mức method:

- `GET /api/books/latest` → `BookController.latest()`.
- `GET /api/books/42` → `BookController.byId("42")`.

Khi `GET /api/books/latest` đi vào, cả pattern literal `/latest` và biến `/{id}` có thể tương thích với đoạn path đó, nhưng **pattern literal cụ thể hơn được ưu tiên**, nên handler `latest()` được chọn. Đây không phải vì phương thức `latest()` được viết trước trong source file.

Annotation rút gọn `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping` là các dạng chuyên biệt của `@RequestMapping` theo HTTP method.

### 3.2. `BeanNameUrlHandlerMapping` và `SimpleUrlHandlerMapping`

Các chiến lược này thường gặp trong code Spring MVC truyền thống hoặc infrastructure:

- `BeanNameUrlHandlerMapping` có thể gắn URL với một bean mang tên hoặc alias dạng URL; ngày nay ít được dùng trực tiếp trong REST code annotation.
- `SimpleUrlHandlerMapping` ánh xạ URL pattern đến handler được cấu hình rõ ràng. Spring MVC có thể dùng các mapping theo kiểu này cho một số infrastructure, ví dụ phục vụ static resources hoặc forward tới default servlet tùy cấu hình.

Một snippet cấu hình `SimpleUrlHandlerMapping` dưới đây nhằm giúp nhận diện API, **không phải một ứng dụng chạy độc lập**:

```java
SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
mapping.setUrlMap(java.util.Map.of("/health-legacy",
        (org.springframework.web.HttpRequestHandler) (request, response) -> {
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write("ok");
        }));
mapping.setOrder(1);
```

Đoạn này cần các import/dependency Spring MVC, Servlet và phải được Spring đăng ký thành bean thích hợp. Để phản hồi `HttpRequestHandler`, `DispatcherServlet` sẽ cần `HttpRequestHandlerAdapter`. Không nên tự thay thế toàn bộ cơ chế `RequestMappingHandlerMapping` chỉ để định nghĩa REST endpoint đơn giản.

### 3.3. `RouterFunctionMapping`: Spring MVC functional endpoints

Spring MVC còn có WebMvc.fn, cho phép khai báo route bằng hàm. `RouterFunctionMapping` tìm `RouterFunction` có predicate khớp rồi chọn `HandlerFunction` tương ứng; `HandlerFunctionAdapter` sẽ thực thi handler.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
public class FunctionalRouteConfig {
    @Bean
    RouterFunction<ServerResponse> greetingRoute() {
        return route()
                .GET("/functional/hello",
                        request -> ServerResponse.ok().body("hello fn"))
                .build();
    }
}
```

Đây là **class cấu hình bổ sung**, cần application MVC đã có. Functional routes trên **Servlet stack** không biến server thành WebFlux. Phân biệt hai cách chọn:

- Với annotated controllers, `RequestMappingHandlerMapping` chọn mapping phù hợp nhất theo các điều kiện và phép so sánh tương ứng.
- Trong **một `RouterFunction` đã tổ hợp**, các functional route được đánh giá theo thứ tự định nghĩa; nên đặt điều kiện cụ thể trước điều kiện rộng.

## 4. Các tiêu chí Spring MVC dùng để so khớp request

`@RequestMapping` và các annotation chuyên biệt có thể mô tả nhiều điều kiện. Một method chỉ được chọn khi **tập điều kiện cần thiết** đều phù hợp, không chỉ vì URL giống nhau.

| Điều kiện | Ví dụ | Kiểm tra gì? |
| --- | --- | --- |
| Path pattern | `@GetMapping("/{id}")` | Đường dẫn tương ứng trong ứng dụng |
| HTTP method | `@GetMapping`, `@PostMapping` | GET hay POST... |
| Query params | `params = "view=compact"` | Query parameter và giá trị |
| Headers | `headers = "X-Client=mobile"` | HTTP header theo điều kiện |
| Consumes | `consumes = "application/json"` | Media type request body, thường từ `Content-Type` |
| Produces | `produces = "application/json"` | Media type response có thể tạo, thương lượng với `Accept` |
| Custom request condition | HandlerMapping mở rộng | Điều kiện do ứng dụng tự bổ sung khi thực sự cần |

**Quan trọng:** `Content-Type` và `Accept` có ý nghĩa khác nhau:

- `Content-Type: application/json` mô tả định dạng **body client gửi lên**. Nó chủ yếu tương tác với `consumes`.
- `Accept: application/json` thể hiện định dạng **client muốn nhận**. Nó chủ yếu tương tác với `produces`.

Ví dụ:

```java
@PostMapping(
    path = "/orders",
    consumes = "application/json",
    produces = "text/plain"
)
public String create(@RequestBody CreateOrderRequest input) {
    return "created:" + input.id();
}
```

Đây là **fragment** nằm trong một `@RestController` với record `CreateOrderRequest(String id)` và cấu hình message converter thích hợp. Điều kiện mapping cho phép yêu cầu có JSON request body và client chấp nhận text response. Nếu `Content-Type` không phù hợp có thể nhận 415; nếu response media type không đáp ứng `Accept` có thể nhận 406.

### 4.1. Query parameter condition

Xét:

```java
@GetMapping(path = "/reports", params = "mode=compact")
public String compact() {
    return "compact";
}

@GetMapping(path = "/reports", params = "!mode")
public String normal() {
    return "normal";
}
```

Đây là **hai method trong cùng controller**. Với `GET /reports?mode=compact`, method thứ nhất phù hợp. Với `GET /reports` (không có query param `mode`), method thứ hai phù hợp. Với `GET /reports?mode=full`, cả hai điều kiện trên đều không khớp; trong cấu hình này Spring có thể trả lỗi điều kiện tham số (thường HTTP 400), **không nên tự kết luận mọi lần không chọn được method đều là 404**.

Các cách biểu diễn khác:

- `params = "debug"`: phải có tham số `debug`.
- `params = "!debug"`: không được có tham số `debug`.
- `params = "mode=compact"`: phải có tham số và giá trị khớp.
- `params = "mode!=compact"`: điều kiện phủ định, theo ngữ nghĩa request condition của Spring.

### 4.2. Điều kiện header và content negotiation

`headers = "X-Tenant=alpha"` so header; `headers = "X-Tenant"` yêu cầu header hiện diện. Không nên dùng `headers` tùy tiện thay cho `consumes`/`produces` khi muốn mô tả media type, vì hai thuộc tính chuyên biệt phản ánh rõ request body format và response content negotiation.

Ví dụ cùng một URL có các biểu diễn kết quả khác nhau có thể đăng ký bằng `produces`, miễn không tạo mapping thực tế mơ hồ. Client nên gửi `Accept` cụ thể khi quan tâm định dạng phản hồi.

## 5. Matching path: literal, biến, wildcard và độ cụ thể

Spring MVC 6.x mặc định sử dụng cơ chế `PathPatternParser` để parse và so khớp URL pattern. Cơ chế `AntPathMatcher` cũ vẫn có trong những ngữ cảnh cấu hình phù hợp, nhưng **không nên suy đoán quy tắc cũ tự động áp dụng** cho Spring 6.x.

Những cú pháp path thường gặp:

| Pattern | Ý nghĩa | Ví dụ khớp |
| --- | --- | --- |
| `/users/new` | Đường dẫn literal | `/users/new` |
| `/users/{id}` | Một path segment và capture `id` | `/users/42` |
| `/assets/*.png` | Wildcard trong một segment | `/assets/icon.png` |
| `/orders/{id:[0-9]+}` | Biến có ràng buộc regex | `/orders/123` |
| `/assets/**` | Không hoặc nhiều segment ở **cuối** pattern | `/assets/css/site.css` |
| `/files/{*path}` | Capture phần path còn lại tại **cuối** pattern | `/files/a/b.txt` |

Với `PathPatternParser`, `**` và `{*path}` chỉ được đặt ở cuối pattern. Pattern kiểu `/a/**/b` không hợp lệ theo các quy tắc của parser đó. Dạng regex `{id:[0-9]+}` giúp tránh việc endpoint dành cho số ID vô tình nhận chuỗi tùy ý; việc **chuyển từ String sang long** diễn ra về sau trong argument resolution/conversion.

Ví dụ đường đi:

```text
Đã đăng ký:
  GET /api/products/latest  -> latest()
  GET /api/products/{id}    -> getById(id)
  GET /api/products/**      -> fallback(...)

Nhận GET /api/products/latest
  -> literal /latest thắng pattern biến và wildcard.

Nhận GET /api/products/123
  -> /{id} cụ thể hơn /**.

Nhận GET /api/products/123/reviews
  -> pattern /** có thể khớp nếu fallback được cấu hình.
```

Trong so sánh path, pattern cụ thể hơn thường được ưu tiên dựa trên wildcard, số biến URI và độ dài. Tuy nhiên, đây **không phải** quy tắc “method nào ở trên file Java thì chạy trước”; phép so sánh `RequestMappingInfo` còn xét các request conditions khác.

### 5.1. URL bên ngoài, context path và servlet path

Một request có thể đi qua nhiều tiền tố:

```text
http://localhost:8080/catalog/api/products/42
                      |       |
                 context path  controller mapping

Nếu DispatcherServlet mapping "/":
  context path: /catalog
  mapping trong controller: /api/products/{id}
  captured id: 42
```

Nếu `DispatcherServlet` được map bằng prefix khác hoặc ứng dụng đổi base path qua server configuration, cần phân tích path mà MVC nhìn thấy trong cấu hình đó. Không đưa context path vào `@RequestMapping` theo thói quen, vì nó thuộc URL triển khai bên ngoài.

### 5.2. Path variable và query param không giống nhau

`/books/42` có thể capture `id=42` qua `@PathVariable`. `/books?id=42` có query parameter `id=42`, được lấy qua `@RequestParam`. Nếu controller chỉ đăng ký `@GetMapping("/books/{id}")`, Spring không tự thay query param cho path variable.

## 6. `HandlerExecutionChain` và interceptor

Sau khi tìm thấy handler, `HandlerMapping` thường trả một `HandlerExecutionChain`. Chain giữ handler và danh sách `HandlerInterceptor` áp dụng cho request. Interceptor có ba callback phổ biến:

- `preHandle(request, response, handler)`: chạy trước handler; trả `true` để tiếp tục hoặc `false` để dừng phần thực thi còn lại.
- `postHandle(request, response, handler, modelAndView)`: chạy sau khi handler thực thi trong các trường hợp phù hợp.
- `afterCompletion(request, response, handler, exception)`: callback khi hoàn tất xử lý request cho các interceptor đã tham gia theo ngữ nghĩa tương ứng.

Luồng đồng bộ đơn giản:

```text
HandlerMapping.getHandler(request)
       |
HandlerExecutionChain
       |
interceptor A: preHandle
interceptor B: preHandle
       |
HandlerAdapter: gọi handler
       |
interceptor B: postHandle
interceptor A: postHandle
       |
rendering (nếu có view)
       |
interceptor B: afterCompletion
interceptor A: afterCompletion
```

Nếu `preHandle` trả `false`, handler không chạy và các callback còn lại tuân theo điều kiện chain đã thực thi. Với async request, callback không hoàn toàn giống sơ đồ đồng bộ; cần dùng `AsyncHandlerInterceptor` nếu cần hành vi async chuyên biệt.

Đặc biệt với `@ResponseBody` và `ResponseEntity`, response body có thể đã được ghi trong `HandlerAdapter` trước `postHandle`. Vì thế, đừng thiết kế interceptor với giả định luôn còn cơ hội thay đổi response body trong `postHandle`; cân nhắc `ResponseBodyAdvice` cho kiểu yêu cầu đó. Đối với security, Spring khuyến nghị cơ chế bảo vệ tích hợp Servlet filter chain/Spring Security thay vì coi interceptor là lớp bảo mật duy nhất.

### 6.1. Ví dụ quan sát handler đã chọn

Một interceptor thực hành có thể in tên handler method được chọn. Class Java sau **chạy trong dự án Spring Boot MVC ở mục 8**, package giống application:

```java
package example.mapping;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MappingTraceConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new SelectedHandlerInterceptor());
    }

    static class SelectedHandlerInterceptor implements HandlerInterceptor {
        @Override
        public boolean preHandle(HttpServletRequest request,
                                 HttpServletResponse response,
                                 Object handler) {
            if (handler instanceof HandlerMethod method) {
                System.out.println("Selected "
                        + method.getBeanType().getSimpleName()
                        + "#" + method.getMethod().getName());
            }
            return true;
        }
    }
}
```

Ví dụ handler được chọn là `ItemsController.latest()`, dòng console ứng với request đó sẽ có dạng:

```text
Selected ItemsController#latest
```

Vì class được đăng ký qua `WebMvcConfigurer`, interceptor nhận các request do MVC mapping xử lý trong phạm vi cấu hình hiện tại. Handler không nhất thiết luôn là `HandlerMethod`, do đó kiểm tra `instanceof` trước khi ép kiểu.

## 7. Nhiều `HandlerMapping` và thứ tự ưu tiên

`DispatcherServlet` có thể nhận nhiều bean `HandlerMapping`. Chúng được sắp xếp theo thứ tự; Spring thử chúng đến khi một mapping cung cấp chain phù hợp. Trong ngữ nghĩa `Ordered`, số `order` **càng nhỏ thì mức ưu tiên càng cao**.

Ví dụ kiến trúc:

```text
DispatcherServlet
  |
  +-- RequestMappingHandlerMapping  -> controllers annotation
  |
  +-- RouterFunctionMapping         -> MVC.fn routes
  |
  +-- các mapping cho resources     -> static assets
  |
  +-- default servlet forwarding    -> fallback nếu bật
```

**Sơ đồ phân loại, không cố định số `order`**: thứ tự và các bean thực tế phụ thuộc framework version, cấu hình MVC, Spring Boot và customization. Trong một `HandlerMapping`, việc chọn route là bài toán **độ cụ thể của request mapping**; giữa các `HandlerMapping` khác nhau, dispatcher dựa trên **thứ tự mapping bean**. Đừng trộn hai khái niệm.

Một fallback rất rộng như `/**` có thể che khuất endpoint hoặc static resource nếu cấu hình sai ưu tiên. Ngược lại, static resource mapping có thể được kiểm tra sau annotation mapping để controller được ưu tiên khi đúng cấu hình. Không tự đặt `order` quá cao cho custom handler mapping trước khi hiểu tất cả mapping hiện hữu.

## 8. Ví dụ Spring MVC hoàn chỉnh với Java 17+

Ví dụ dùng **Spring Boot 3.4.0**, Java 17 và Spring MVC. Đây là dự án độc lập để thấy cách `RequestMappingHandlerMapping` chọn method qua HTTP request. Chỉ cần Spring Web starter; Spring Boot cung cấp sẵn embedded Servlet container và `DispatcherServlet`.

### 8.1. Cấu trúc

```text
mapping-demo/
├── pom.xml
└── src/
    ├── main/java/example/mapping/
    │   ├── MappingDemoApplication.java
    │   ├── ItemsController.java
    │   └── MappingTraceConfiguration.java
    └── test/java/example/mapping/
        └── ItemsMappingTest.java
```

`MappingTraceConfiguration` là class ở mục 6.1. Nếu không muốn in log handler, có thể không tạo file đó; hành vi chọn route của controller vẫn giữ nguyên.

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mapping-demo</artifactId>
    <version>1.0.0</version>
    <name>mapping-demo</name>

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
```

Boot quản lý version các dependency Spring phù hợp với Boot 3.4.0. Dùng Maven chạy từ thư mục chứa `pom.xml`. Không tự thêm `@EnableWebMvc` vào demo vì Boot đã tự cấu hình MVC thích hợp.

### 8.3. Điểm khởi chạy

File `src/main/java/example/mapping/MappingDemoApplication.java`:

```java
package example.mapping;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MappingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingDemoApplication.class, args);
    }
}
```

### 8.4. Các route và điều kiện rõ ràng

File `src/main/java/example/mapping/ItemsController.java`:

```java
package example.mapping;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemsController {

    @GetMapping(path = "/latest", produces = MediaType.TEXT_PLAIN_VALUE)
    public String latest() {
        return "item:latest";
    }

    @GetMapping(path = "/{id}", produces = MediaType.TEXT_PLAIN_VALUE)
    public String byId(@PathVariable String id) {
        return "item:" + id;
    }

    @GetMapping(params = "!view", produces = MediaType.TEXT_PLAIN_VALUE)
    public String listDefault() {
        return "list:default";
    }

    @GetMapping(params = "view=compact",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String listCompact() {
        return "list:compact";
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String create(@RequestBody NewItem input) {
        return "created:" + input.name();
    }

    public record NewItem(String name) {
    }
}
```

Giải thích:

- `@RequestMapping("/api/items")` trên class là prefix chung.
- `latest()` và `byId(...)` có cùng HTTP method và cùng tiền tố; literal `/latest` được ưu tiên khi khớp.
- `listDefault()` cần **không có** tham số `view`, `listCompact()` cần `view=compact`; chúng không tạo xung đột khi khớp request được thiết kế.
- `create(...)` chỉ xử lý **POST** với `Content-Type: application/json`; body được parse thành record `NewItem` nếu JSON hợp lệ. Nó trả text và phản hồi thành công mặc định là HTTP 200 vì demo không dùng `@ResponseStatus`.
- `@RequestBody` và Jackson chạy sau bước chọn mapping khi `HandlerAdapter` thực thi method; `HandlerMapping` không tự đọc thành record `NewItem`.

### 8.5. Chạy và kiểm chứng bằng HTTP request

Yêu cầu: JDK 17+, Maven, cổng 8080 đang rảnh. Từ thư mục `mapping-demo`:

```bash
mvn test
mvn spring-boot:run
```

Lệnh chạy app sẽ giữ terminal mở; mở terminal khác để gọi:

```bash
curl -s http://localhost:8080/api/items/latest
curl -s http://localhost:8080/api/items/42
curl -s http://localhost:8080/api/items
curl -s "http://localhost:8080/api/items?view=compact"
curl -s -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: text/plain" \
  -d '{"name":"Lan"}'
```

Tương ứng từng command trên, **body** dự kiến:

```text
item:latest
item:42
list:default
list:compact
created:Lan
```

Đây là năm kết quả của **năm request khác nhau**, mỗi response body không nhất thiết có newline ở cuối. Nếu cùng tạo file `MappingTraceConfiguration.java`, stdout server còn có các dòng `Selected ItemsController#...`, giúp quan sát method được chọn.

Thử gửi request có method hoặc media type không tương thích:

```bash
curl -i -X PUT http://localhost:8080/api/items/42

curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: text/plain" \
  -d 'Lan'

curl -i http://localhost:8080/api/items/42 \
  -H "Accept: application/xml"
```

Trong demo và cấu hình mặc định:

- `PUT /api/items/42` → thường HTTP **405 Method Not Allowed** (có pattern phù hợp nhưng HTTP method không được hỗ trợ).
- POST có `Content-Type: text/plain` → thường HTTP **415 Unsupported Media Type** do `consumes` không khớp.
- GET cần XML khi handler chỉ `produces=text/plain` → thường HTTP **406 Not Acceptable**.

Body lỗi có thể khác nhau giữa các phiên bản/cấu hình Spring Boot; **mã trạng thái** mới là trọng tâm ở các tình huống này. Các error status là kết quả của quá trình tìm kiếm mapping và xử lý điều kiện, không chứng minh rằng controller business method đã chạy.

### 8.6. Bài test `MockMvc` xác nhận mapping

File `src/test/java/example/mapping/ItemsMappingTest.java`:

```java
package example.mapping;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemsMappingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void picksLiteralPathBeforeVariable() throws Exception {
        mvc.perform(get("/api/items/latest"))
                .andExpect(status().isOk())
                .andExpect(content().string("item:latest"));

        mvc.perform(get("/api/items/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("item:42"));
    }

    @Test
    void matchesQueryConditions() throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isOk())
                .andExpect(content().string("list:default"));

        mvc.perform(get("/api/items").param("view", "compact"))
                .andExpect(status().isOk())
                .andExpect(content().string("list:compact"));
    }

    @Test
    void honorsHttpMethodAndMediaType() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isOk())
                .andExpect(content().string("created:Lan"));
    }
}
```

`MockMvc` mô phỏng request qua Spring MVC infrastructure trong test context, **không cần mở network port thật**. Các assertion buộc ứng dụng phải chọn đúng handler, xử lý request và tạo body dự kiến. Chạy riêng `mvn test`; dự kiến Maven báo test pass, nhưng tổng số test/runtime log tùy plugin và môi trường.

## 9. Quan sát danh sách handler mappings ở startup

Bạn có thể inspect mapping đã đăng ký, thay vì đoán từ annotation. Trong ứng dụng demo ở mục 8, thêm class tùy chọn:

```java
package example.mapping;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@Component
public class MappingInspector implements ApplicationRunner {
    private final RequestMappingHandlerMapping mapping;

    public MappingInspector(RequestMappingHandlerMapping mapping) {
        this.mapping = mapping;
    }

    @Override
    public void run(ApplicationArguments args) {
        mapping.getHandlerMethods().forEach((info, method) ->
                System.out.println(info + " -> "
                        + method.getBeanType().getSimpleName()
                        + "#" + method.getMethod().getName()));
    }
}
```

Lúc khởi động, code liệt kê metadata `RequestMappingInfo` và `HandlerMethod` đang có trong `RequestMappingHandlerMapping`. Cú pháp `toString()` của `RequestMappingInfo` có thể khác nhau theo Spring version, thứ tự traversal cũng không phải hợp đồng API; **không so sánh nguyên văn stdout hay thứ tự các dòng**. Điều đáng quan sát là mỗi URL/method/điều kiện từ `ItemsController` hiện diện đúng trong registry.

Nếu muốn debug bằng logger:

```properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
```

Đây là **nội dung mẫu của `src/main/resources/application.properties`**, không phải file Java. Mức TRACE/DEBUG có thể làm log nhiều; dùng tạm cho môi trường học tập và trả log về mức phù hợp khi triển khai. Đọc startup logs, mappings và request logs cùng nhau sẽ cho bằng chứng mạnh hơn chỉ nhìn HTTP status.

## 10. Không tìm thấy hoặc không chọn được handler: phân biệt lỗi

Không nên gộp mọi vấn đề về mapping thành “404”:

| Hiện tượng | Ý nghĩa cần điều tra | Hướng kiểm tra |
| --- | --- | --- |
| 404 Not Found | Không có handler thích hợp cho path hoặc request bị xử lý/fallback theo cấu hình khác | Context path, servlet mapping, controller scan, URL pattern |
| 405 Method Not Allowed | Path có mapping nhưng HTTP method không phù hợp | `@GetMapping` / `@PostMapping`, client method |
| 415 Unsupported Media Type | Request body media type không phù hợp điều kiện `consumes` hoặc converter | `Content-Type`, `consumes`, message converters |
| 406 Not Acceptable | Không đáp ứng định dạng mà client có thể nhận | `Accept`, `produces`, converters |
| 400 Bad Request | Có thể do `params` conditions hoặc request parameter/body không hợp lệ | Query params, type conversion, JSON/binding |
| 500 hoặc lỗi khởi động | Mapping xung đột, cấu hình handler/bean không hợp lệ, lỗi thực thi | Root cause trong startup/runtime logs |

Các mã là **khả năng điển hình** trong Spring MVC; fallback handlers, exception resolvers, security filters hoặc custom error handlers có thể đổi biểu hiện. Thấy một status chưa đủ để suy ra duy nhất nguyên nhân.

### 10.1. Controller không được đăng ký

`@RestController` không đảm bảo class đó được quét. Với Boot, `@SpringBootApplication` bao gồm component scanning từ package tương ứng. Nếu `ItemsController` nằm ngoài package scan, `RequestMappingHandlerMapping` không có mapping nào của nó. Giải pháp là tổ chức package hợp lý hoặc cấu hình scan cụ thể, tránh quét bừa toàn classpath.

### 10.2. Trùng mapping hoặc ambiguous handler methods

Ví dụ hai method trong cùng context cùng khai báo `@GetMapping("/orders/{id}")` với các điều kiện khác không phân biệt được:

```java
@GetMapping("/orders/{id}")
public String first(@PathVariable String id) {
    return "first:" + id;
}

@GetMapping("/orders/{id}")
public String second(@PathVariable String id) {
    return "second:" + id;
}
```

Đây là **fragment cố tình sai**: trong cùng một controller, Spring thường phát hiện mapping trùng khi đăng ký và báo lỗi startup. Với hai pattern khác chuỗi nhưng cùng mức độ cụ thể (ví dụ `/{id}` và `/{name}`), có trường hợp request khớp cả hai và runtime báo **ambiguous handler methods**. Đổi tên Java method, đổi tên biến URI hoặc di chuyển method trong file **không phải cách khử ambiguity đáng tin**. Hãy thiết kế path, method, params, headers hoặc consumes/produces có ý nghĩa, tránh tạo hai mapping cạnh tranh.

### 10.3. Path pattern quá rộng

Một fallback `/**` có thể khớp nhiều request. Trong cùng annotation mapping, pattern cụ thể hơn thường thắng; giữa các mapping bean, thứ tự ưu tiên còn quyết định mapping nào được thử trước. Nếu trang static asset hoặc endpoint health đi sai handler, inspect danh sách `HandlerMapping`, resource configuration và thứ tự `Ordered` thực tế.

### 10.4. Lẫn `HandlerMapping` với `HandlerInterceptor`

Interceptor chỉ chạy trong execution chain sau khi mapping tương ứng chọn handler. Một request không tới dispatcher, bị Servlet filter chặn hoặc không được mapping xử lý có thể không kích hoạt interceptor bạn mong đợi. Nếu cần xử lý bảo mật và logging xuyên suốt từ trước dispatch, hãy đánh giá Servlet filter hoặc Spring Security theo trách nhiệm.

### 10.5. Nhầm routing MVC với WebFlux

Cả hai stack có `@GetMapping`, nhưng MVC dùng `DispatcherServlet`, `RequestMappingHandlerMapping` thuộc package `org.springframework.web.servlet...` và `RequestMappingHandlerAdapter` của Servlet stack. WebFlux dùng `DispatcherHandler` và các thành phần reactive thuộc `org.springframework.web.reactive...`. Dù tên lớp có thể giống nhau, chúng **không thể hoán đổi chỉ vì annotation giống nhau**.

## 11. Bài tập suy luận HandlerMapping

### Bài 1 — chọn literal hay path variable

Giả sử:

```java
@GetMapping("/customers/new")
public String newCustomer() { return "new"; }

@GetMapping("/customers/{id}")
public String customer(@PathVariable String id) { return id; }
```

Dự đoán handler cho `GET /customers/new` và `GET /customers/123`. Vì sao vị trí hai method trong file không quyết định thứ tự? **Gợi ý:** pattern literal cụ thể hơn so với một biến path segment.

### Bài 2 — phân biệt path và HTTP method

Controller chỉ có `@GetMapping("/invoices/{id}")`. Dự đoán hành vi khi client gửi `POST /invoices/10`. Vì sao đây thường là 405 thay vì 404? Đổi thành `@RequestMapping("/invoices/{id}")` không chỉ là đổi tên annotation: nếu không khai báo điều kiện method, phạm vi phương thức HTTP được nhận sẽ rộng hơn, có thể ngoài ý muốn.

### Bài 3 — phân biệt `consumes` và `produces`

Một endpoint nhận JSON và trả plain text. Viết `@PostMapping` với `consumes="application/json"` và `produces="text/plain"`. Dự đoán hậu quả khi client gửi `Content-Type:text/plain`, và khi client gửi `Accept:application/xml`. Trường hợp nào liên quan request body, trường hợp nào liên quan response media type?

### Bài 4 — phân tích chuỗi thực thi

Giải thích vì sao một request có thể đã chọn được handler nhưng vẫn lỗi trước khi body response hoàn tất. Đưa ra hai nguyên nhân xảy ra **sau HandlerMapping**, ví dụ lỗi conversion của `@PathVariable long` hoặc lỗi do service/controller ném exception.

### Bài 5 — thiết kế route tránh ambiguity

Giả sử bạn muốn `GET /reports` mặc định và `GET /reports?view=compact`. Thiết kế hai mapping có query condition rõ ràng, sau đó thử trường hợp `?view=full`. Có cần endpoint fallback nào khác không? Hãy lựa chọn dựa trên API contract mong muốn.

## 12. Tài liệu chính thức để đào sâu

- Tổng quan `DispatcherServlet` và quá trình xử lý: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/sequence.html
- Mapping annotated controller, request conditions và path pattern: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Servlet MVC `HandlerMapping` và special bean types: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/special-bean-types.html
- Interceptor trong Servlet MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Functional endpoints trên Servlet stack: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-functional.html
- API `RequestMappingHandlerMapping`: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerMapping.html

**Ghi nhớ:** `HandlerMapping` quyết định **handler nào** và các interceptor liên quan; `HandlerAdapter` quyết định **cách thực thi handler đó**. Với controller annotation, việc chọn handler phụ thuộc **toàn bộ điều kiện request**, không chỉ path; Spring dùng các quy tắc độ cụ thể và ưu tiên rõ ràng để tránh quyết định theo thứ tự code.
