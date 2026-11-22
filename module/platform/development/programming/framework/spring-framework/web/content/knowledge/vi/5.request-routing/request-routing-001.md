# @Controller, @RestController và cơ chế phát hiện controller trong Spring Web

Trong Spring Web, **controller** là đối tượng Spring (bean) tham gia tiếp nhận request HTTP, gọi nghiệp vụ và quyết định kết quả trả về. Hai annotation dễ gặp nhất là **@Controller** và **@RestController**. Chúng cùng xác định một lớp có vai trò controller, nhưng **khác cách Spring diễn giải giá trị trả về từ handler method**.

Bài học thuộc nhóm **Định tuyến yêu cầu** nên cần phân biệt hai bước xảy ra trước khi request đến method: **Spring phát hiện/đăng ký controller thành bean**, sau đó **Spring MVC đăng ký các request mapping** của những bean phù hợp. Đánh dấu class bằng annotation chỉ là điều kiện để framework nhận diện; controller còn phải nằm trong ApplicationContext đang phục vụ request và có method được ánh xạ.

Mục tiêu sau bài:

- Phân biệt chính xác **@Component, @Controller, @RestController và @ResponseBody**.
- Giải thích tại sao có class @RestController nhưng gọi URL vẫn nhận **404**.
- Mô tả cơ chế **component scan → bean definition → controller detection → handler mapping → request dispatch**.
- Chọn **view name** hay **response body** đúng theo yêu cầu ứng dụng.
- Tổ chức package, khai báo mapping, kiểm chứng bằng một ví dụ Spring Boot MVC có thể chạy được.
- Biết giới hạn của controller detection khi dùng context nhiều tầng, proxy và web stack khác nhau.

## 1. Controller nằm ở đâu trong Spring MVC?

Một HTTP request không được đưa trực tiếp đến method chỉ vì tên method giống URL. Spring MVC đi qua **DispatcherServlet**, chọn handler qua **HandlerMapping**, rồi gọi handler bằng **HandlerAdapter** và xử lý kết quả trả về.

~~~text
Client HTTP request
       |
Servlet container / Servlet filter chain
       |
DispatcherServlet
       |
RequestMappingHandlerMapping
       |      (đã phát hiện và đăng ký controller mappings)
       v
Chọn handler theo path, HTTP method,
Content-Type, Accept, params, headers...
       |
RequestMappingHandlerAdapter
       |-- resolve arguments: @PathVariable, @RequestParam,
       |   @RequestBody, Model, Servlet request, ...
       v
@Controller / @RestController handler method
       |
       +-- Model + view name -> ViewResolver -> HTML
       |
       +-- @ResponseBody / @RestController
       |      -> HttpMessageConverter -> JSON/text/...
       |
       +-- ResponseEntity -> status + headers + body
       |
HTTP response
~~~

Đây là luồng rút gọn của **Spring MVC trên Servlet stack**. Với Spring WebFlux, các annotation controller quen thuộc vẫn được hỗ trợ nhưng hạ tầng bên dưới là WebFlux HandlerMapping/HandlerAdapter, **DispatcherHandler** và reactive codecs. Cách phát hiện/controller mapping có những ý tưởng tương tự, còn mô hình I/O khác nhau.

**Hai bước không được nhập làm một:**

1. **Bean discovery/registration:** lớp Java được đưa vào Spring ApplicationContext dưới dạng bean.
2. **Request mapping registration:** Spring MVC xem xét các controller beans, tìm @RequestMapping hoặc @GetMapping/@PostMapping... rồi đăng ký các điều kiện HTTP tương ứng.

Một class có thể là Spring bean nhưng **không phải HTTP controller**; một class có @Controller nhưng **không được đăng ký thành bean trong đúng context** cũng không thể phục vụ request.

## 2. @Controller là gì?

**@Controller** thuộc package **org.springframework.stereotype**. Đây là một stereotype annotation đánh dấu loại thành phần web, được meta-annotated với **@Component**, nên nằm trong nhóm mặc định mà Spring component scan có thể phát hiện.

~~~java
package example.web;

import org.springframework.stereotype.Controller;

@Controller
public class HomeController {
}
~~~

Đây chỉ là **khai báo một controller bean tiềm năng**, chưa có endpoint: không có @GetMapping hoặc mapping nào khác.

Khi thêm handler:

~~~java
@Controller
public class HomeController {

    @GetMapping("/home")
    public String home() {
        return "home";
    }
}
~~~

Đoạn này **minh họa**, chưa độc lập: còn cần import @GetMapping, MVC context, view resolver và template/view tên **home**. Trong Spring MVC truyền thống, giá trị String **"home"** được hiểu là **tên view** để ViewResolver giải quyết. Nếu có template phù hợp, view sẽ được render thành HTML.

### Không phải mọi giá trị trả về của @Controller đều là tên view

Với @Controller, Spring MVC có nhiều return-value handler. Kết quả phụ thuộc **annotation trên method, kiểu dữ liệu trả về và MVC configuration**:

- **String** hoặc **View** trong handler thông thường: thường biểu thị view name hoặc View.
- **ModelAndView**: chỉ rõ view và model.
- **Model** hoặc **@ModelAttribute**: dùng cho dữ liệu model theo quy tắc MVC.
- **@ResponseBody**: đưa return value vào HTTP response body.
- **ResponseEntity<T>**: mang status, headers và body, có thể ghi body **ngay cả khi class chỉ dùng @Controller**.
- **redirect:** hoặc **forward:** trong view name: tạo redirect/forward theo cơ chế view resolution.

Vì vậy không nên kết luận “@Controller thì tuyệt đối không thể trả JSON”. @Controller **có thể trả JSON**, chỉ cần sử dụng kiểu/annotation trả response body đúng.

## 3. @RestController là gì?

**@RestController** thuộc package **org.springframework.web.bind.annotation** và là một **composed annotation** có hai ý nghĩa chính:

~~~text
@RestController
    ≈ @Controller
    + @ResponseBody ở cấp class
~~~

Ký hiệu ≈ thể hiện **tương đương về semantics chính**, không phải định nghĩa đầy đủ từng thuộc tính của annotation.

~~~java
package example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/api/status")
    public Status status() {
        return new Status("ok");
    }

    public record Status(String value) {
    }
}
~~~

Đây là **đoạn controller minh họa** cần ApplicationContext MVC/Boot và JSON converter thích hợp, không phải chương trình Java chạy độc lập. Nếu được đăng ký và có Jackson hỗ trợ record, endpoint trả body JSON tương đương:

~~~json
{"value":"ok"}
~~~

Khác với @Controller trả tên view, các handler của @RestController mặc định có semantics **@ResponseBody**: đối tượng được chuyển thành biểu diễn HTTP qua các **HttpMessageConverter** (MVC) thay vì chuyển tới ViewResolver.

### So sánh ngắn gọn

| Tiêu chí | @Controller | @RestController |
|---|---|---|
| Thuộc nhóm stereotype Spring | Có; meta-annotated @Component | Có; meta-annotated @Controller và @ResponseBody |
| Được component scan phát hiện | Có khi trong vùng scan và bộ lọc phù hợp | Có trong cùng điều kiện |
| Có thể chứa @GetMapping/@PostMapping | Có | Có |
| String trả về mặc định | Thường là **view name** | **Response body** chuỗi String |
| Trả object JSON mặc định | Cần @ResponseBody/ResponseEntity hoặc cơ chế thích hợp | Qua response body converter khi JSON được hỗ trợ |
| Dùng Model + template HTML | Phù hợp tự nhiên | Không phù hợp nếu muốn String được hiểu là view name |
| Dùng làm REST API | Được, nếu thêm @ResponseBody | Phổ biến và tiện lợi |
| Có tự tạo server/URL không? | Không | Không |
| Có khác biệt trong cách scan package không? | Không đáng kể ở cấp stereotype | Không đáng kể ở cấp stereotype |

**Lựa chọn theo return semantics:** HTML template phía server thường dùng @Controller; JSON/text API thường dùng @RestController. Cả hai có thể sống trong cùng một ứng dụng Spring MVC.

## 4. @ResponseBody là mấu chốt của khác biệt

**@ResponseBody** yêu cầu framework xử lý giá trị trả về như **HTTP response body**. Có thể đặt trên **method** hoặc **class**.

Cùng mục đích trả API JSON, hai cách dưới đây gần tương đương:

~~~java
@Controller
public class ProfileController {

    @ResponseBody
    @GetMapping("/api/profile")
    public Profile profile() {
        return new Profile(7, "An");
    }

    public record Profile(int id, String name) {
    }
}
~~~

~~~java
@RestController
public class ProfileController {

    @GetMapping("/api/profile")
    public Profile profile() {
        return new Profile(7, "An");
    }

    public record Profile(int id, String name) {
    }
}
~~~

**Đây là hai phiên bản thay thế nhau**, không được đồng thời tạo hai class cùng tên/mapping trong một project. Cần import annotation, dependency Spring Web và converter JSON phù hợp.

Cả hai trả một đối tượng được serialize, ví dụ:

~~~json
{"id":7,"name":"An"}
~~~

Trong Spring MVC, **RequestResponseBodyMethodProcessor** là một trong các cơ chế xử lý kiểu return này và phối hợp các **HttpMessageConverter** với media type. JSON converter thường đến từ Jackson. Nếu dự án không có converter hỗ trợ kiểu return và media type, Spring không thể tự tạo JSON chỉ vì xuất hiện @RestController.

### Trường hợp String dễ nhầm

~~~java
@Controller
class HtmlController {

    @GetMapping("/welcome")
    public String welcome() {
        return "welcome";
    }
}
~~~

Spring MVC có thể tìm view **welcome**; cần template/view đã cấu hình. Còn:

~~~java
@RestController
class TextController {

    @GetMapping("/welcome")
    public String welcome() {
        return "welcome";
    }
}
~~~

Spring MVC ghi body văn bản **welcome** (nếu mapping phù hợp), **không tìm template welcome**. Hai ví dụ là **lựa chọn riêng**, không tạo cùng URL trong một app nếu không chủ ý xử lý khác điều kiện.

Lỗi phổ biến là đổi một class @Controller thành @RestController để “sửa 404” rồi thấy browser hiển thị chữ **home** thay vì trang HTML. Khi đó nguyên nhân là **thay đổi cách xử lý return value**, chưa chắc đã sửa chuyện scan/mapping.

### ResponseEntity là trường hợp đặc biệt

~~~java
@Controller
class HealthController {

    @GetMapping("/check")
    public ResponseEntity<String> check() {
        return ResponseEntity.ok()
                .header("X-Check", "passed")
                .body("OK");
    }
}
~~~

**Phải import** @Controller, @GetMapping và **org.springframework.http.ResponseEntity** khi đưa đoạn method minh họa vào project. ResponseEntity được MVC xử lý như một kiểu return đặc biệt, nên **không cần @ResponseBody** trên method mới ghi được body "OK". Kết quả: status 200, X-Check: passed, body OK.

Tuy vậy, dùng @RestController thường rõ ý đồ hơn khi cả class chỉ chứa API endpoints.

## 5. Cơ chế phát hiện controller: từ class tới bean

### Bước A — Spring tìm candidate components

Ở Java configuration, ví dụ:

~~~java
@Configuration
@ComponentScan("example.web")
class WebConfig {
}
~~~

Đây là **đoạn cấu hình**, cần import @Configuration và @ComponentScan. Trong lúc khởi tạo ApplicationContext, Spring quét các class có stereotype phù hợp dưới **example.web** và các subpackages theo quy tắc component scanning. Spring dùng metadata của class để xác định candidate và đăng ký **BeanDefinition**.

Mặc định, các annotation thuộc họ **@Component** như **@Service**, **@Repository**, **@Controller**, **@Configuration**, và **@RestController** (qua meta-annotations) có thể được phát hiện.

**Tức là:** @RestController được phát hiện vì nó **gián tiếp mang @Component**, chứ không phải vì Spring Boot liên tục tìm mọi tên class kết thúc bằng "Controller".

Ví dụ:

~~~text
example/
  web/
    StatusController.java       <-- @RestController, nằm trong scan
  service/
    GreetingService.java        <-- @Service, ngoài vùng "example.web"
  another/
    OtherController.java        <-- @Controller, ngoài vùng "example.web"
~~~

Nếu cấu hình chỉ scan **example.web**, hai class ngoài package này không tự được đưa vào context bằng việc quét ấy. Vẫn có thể đăng ký thủ công hoặc thông qua cấu hình khác, nhưng **không được kết luận chúng đã được scan**.

### Bước B — BeanDefinition được tạo, bean được khởi tạo

Sau khi xác định component, Spring lưu cấu hình bean và thực hiện quá trình tạo/phụ thuộc/lifecycle theo loại bean và scope. Bean có thể được:

- Quét bởi **@ComponentScan** hoặc **context:component-scan** trong XML.
- Đăng ký qua **@Bean** của @Configuration.
- Import từ cấu hình khác bằng **@Import**.
- Đăng ký lập trình bằng API của ApplicationContext/registry.

**@Controller không buộc bạn phải dùng component scan.** Một object controller có thể được đăng ký theo cách khác, miễn Spring MVC nhìn thấy nó là controller bean hợp lệ trong đúng context.

### Bước C — Spring MVC xác định bean nào là handler

Khi MVC infrastructure khởi tạo, **RequestMappingHandlerMapping** (hoặc hạ tầng mapping tương ứng) tìm các bean types được xem là **handler**, điển hình những type có **@Controller** kể cả qua meta-annotation như @RestController. Framework kiểm tra các method có @RequestMapping hoặc composed mappings như @GetMapping, @PostMapping.

Ví dụ:

~~~java
@Service
class LibraryService {

    @GetMapping("/books")
    public String list() {
        return "data";
    }
}
~~~

Đây là **đoạn minh họa lỗi thiết kế**. Dù @Service được scan thành bean và method có @GetMapping, Spring MVC **không coi nó là annotated controller chỉ nhờ @GetMapping**. Không nên đặt handler annotation vào @Service rồi kỳ vọng tự tạo endpoint. Hãy có @Controller/@RestController gọi service và ánh xạ URL.

### Bước D — Đăng ký mappings

Một handler method thường tạo metadata chứa:

- URL path/pattern.
- HTTP method: GET, POST, PUT, DELETE, PATCH...
- **params**: điều kiện query/form parameter khi có.
- **headers**: điều kiện header khác khi có.
- **consumes**: media type của request body.
- **produces**: media type response được client chấp nhận.
- Các yêu cầu custom conditions hoặc API version tùy cấu hình/framework version.

Mapping kết hợp các điều kiện ở **class level** và **method level**. Nếu có hai mapping trùng không thể phân biệt ở cùng môi trường, ứng dụng có thể báo lỗi **Ambiguous mapping** trong startup; những mapping chồng lấp nhưng khác độ cụ thể có thể chỉ gây mơ hồ ở lúc request, tùy cấu hình.

### Bước E — DispatcherServlet dispatch request

Khi request đến, Spring đánh giá mapping đã đăng ký, chọn handler method thích hợp, bind method arguments, gọi controller và xử lý kết quả. **Không quét lại toàn bộ classpath để tìm controller cho từng request**.

Điều này giải thích vì sao sửa source code và lưu file chưa khiến endpoint mới xuất hiện trong tiến trình Java đang chạy nếu dự án chưa có cơ chế reload/restart tương ứng.

## 6. Spring Boot phát hiện controller như thế nào?

Trong Spring Boot, **@SpringBootApplication** tích hợp những cơ chế cần thiết như **@SpringBootConfiguration**, **@EnableAutoConfiguration** và **@ComponentScan**. Theo mặc định, component scanning bắt đầu ở **package chứa lớp ứng dụng chính** và các subpackages.

Cấu trúc được khuyến khích:

~~~text
src/main/java/
  com/example/shop/
    ShopApplication.java         <-- @SpringBootApplication
    web/
      ProductRestController.java <-- @RestController
      HomeController.java        <-- @Controller
    service/
      ProductService.java        <-- @Service
    config/
      WebConfiguration.java      <-- @Configuration
~~~

Do ShopApplication nằm trong **com.example.shop**, tất cả các package con phù hợp đều nằm trong phạm vi scan mặc định.

**Ví dụ lỗi:**

~~~text
src/main/java/
  com/example/shop/bootstrap/
    ShopApplication.java       <-- @SpringBootApplication
  com/example/shop/web/
    ProductRestController.java <-- @RestController
~~~

Khi đó package mặc định để scan là **com.example.shop.bootstrap** và các package con; **com.example.shop.web** là package anh em, không nằm trong scan. Ứng dụng vẫn có thể khởi động HTTP server nhưng GET tới mapping của ProductRestController trả **404**.

**Sửa hợp lý:**

- Di chuyển ShopApplication lên **com.example.shop** (cấu trúc rõ ràng và dễ duy trì).
- Hoặc khi có lý do thật sự, cấu hình scan rõ bằng @SpringBootApplication(scanBasePackages = "com.example.shop") hoặc @ComponentScan thích hợp. Khi thay đổi scan, cần nhớ những phần khác như entity/repository scan có cơ chế riêng; không suy rằng chỉnh component scan là đủ cho mọi loại metadata.

**Không nên đặt lớp chính vào default package (không có dòng package)**: Spring Boot cảnh báo cấu trúc này có thể khiến classpath scan quá rộng và khó kiểm soát. Dùng package Java có tên rõ ràng.

### Component scan không đồng nghĩa @EnableWebMvc

- **@ComponentScan** phát hiện và đăng ký các bean như controller/service.
- **@EnableWebMvc** bật cấu hình MVC Java trong **Spring MVC thuần**.
- **Spring Boot MVC auto-configuration** thiết lập MVC infrastructure/DispatcherServlet theo điều kiện, nên Boot thông thường **không cần @EnableWebMvc**.

Một dự án có thể scan được @Controller nhưng chưa có DispatcherServlet/web infrastructure hoặc dependency cần thiết. Ngược lại, servlet MVC chạy nhưng không scan được controller cũng không có mapping tương ứng. Khi debug phải xác định **cả hai tầng**.

## 7. Ví dụ Spring Boot MVC hoàn chỉnh: HTML và JSON cùng chạy

Ví dụ này giúp phân biệt **@Controller → Thymeleaf view** và **@RestController → JSON** trong **cùng một ứng dụng**. Dùng **Java 17+**, Maven, Spring Initializr tại **https://start.spring.io/** và chọn dependency:

1. **Spring Web** để chạy Spring MVC.
2. **Thymeleaf** để render HTML template.
3. Có thể thêm **Spring Boot DevTools** trong môi trường phát triển, nhưng không bắt buộc.

Dùng phiên bản Spring Boot được Initializr hỗ trợ và JDK tương thích. **Không dùng Spring Reactive Web** cho ví dụ Servlet MVC này. Trong các bản Boot, artifact starter MVC có thể khác tên (Boot 3.x thường dùng spring-boot-starter-web, Boot 4.x dùng spring-boot-starter-webmvc); chọn qua Initializr để nhận cấu hình phù hợp.

Tạo package nền **example.discovery** trong project. Các file:

~~~text
src/main/
  java/example/discovery/
    DiscoveryApplication.java
    service/GreetingService.java
    web/PageController.java
    web/GreetingRestController.java
    web/MixedController.java
  resources/
    templates/greeting.html
~~~

### 7.1. Lớp ứng dụng chính

**src/main/java/example/discovery/DiscoveryApplication.java**

~~~java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryApplication.class, args);
    }
}
~~~

**Vì sao đặt ở đây:** lớp chính thuộc **example.discovery**, nằm phía trên các package **example.discovery.web** và **example.discovery.service**, nên Spring component scan mặc định có thể phát hiện controller và service. Không cần @ComponentScan tùy biến.

### 7.2. Service chỉ chứa nghiệp vụ

**src/main/java/example/discovery/service/GreetingService.java**

~~~java
package example.discovery.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Service là Spring bean nhưng **không khai báo HTTP endpoint**. Tách logic vào service cho phép HTML controller và JSON controller dùng chung mà không nhân đôi nghiệp vụ.

### 7.3. HTML controller: @Controller và Model

**src/main/java/example/discovery/web/PageController.java**

~~~java
package example.discovery.web;

import example.discovery.service.GreetingService;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PageController {

    private final GreetingService greetingService;

    public PageController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greetingPage(
            @RequestParam(defaultValue = "An") String name,
            Model model) {
        model.addAttribute("message", greetingService.greet(name));
        return "greeting";
    }
}
~~~

Điểm quan trọng:

- **@Controller** làm class thành controller bean.
- **@GetMapping("/greeting")** đăng ký HTTP GET /greeting.
- **@RequestParam** đọc tham số query; defaultValue được dùng khi không truyền tên.
- **Model** lưu giá trị message cho view.
- **return "greeting"** là **logical view name**, được Thymeleaf view resolver liên kết tới template **templates/greeting.html**, không phải body chữ "greeting".

**src/main/resources/templates/greeting.html**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Ví dụ Spring Controller</title>
</head>
<body>
    <h1 th:text="${message}">Thông điệp</h1>
</body>
</html>
~~~

Thymeleaf thay nội dung h1 bằng message có trong Model. **th:text** escape HTML cho dữ liệu hiển thị, phù hợp với văn bản từ request. Hạn chế dùng th:utext cho dữ liệu không tin cậy vì có nguy cơ chèn HTML/script nếu không kiểm soát.

### 7.4. JSON API controller: @RestController

**src/main/java/example/discovery/web/GreetingRestController.java**

~~~java
package example.discovery.web;

import example.discovery.service.GreetingService;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingRestController {

    private final GreetingService greetingService;

    public GreetingRestController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(path = "/{name}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingResponse byName(@PathVariable String name) {
        return new GreetingResponse(greetingService.greet(name));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public GreetingResponse create(@RequestBody GreetingRequest request) {
        return new GreetingResponse(
                greetingService.greet(request.name()));
    }

    public record GreetingRequest(String name) {
    }

    public record GreetingResponse(String message) {
    }
}
~~~

Vì @RestController đã bao gồm @ResponseBody ở mức class, đối tượng GreetingResponse được JSON message converter serialize. **@RequestMapping** ở class kết hợp với **@GetMapping** và **@PostMapping** ở method. Ví dụ trên có hai HTTP mappings khác nhau:

~~~text
GET  /api/greetings/{name}
POST /api/greetings
~~~

**@ResponseStatus(HttpStatus.CREATED)** làm response POST thành status **201** khi xử lý thành công. **consumes** hạn chế Content-Type request; **produces** thể hiện response media type. Bản đơn giản này không validate trường name null/blank; production API nên thêm DTO validation và xử lý lỗi theo contract.

### 7.5. @Controller vẫn trả response body khi cần

**src/main/java/example/discovery/web/MixedController.java**

~~~java
package example.discovery.web;

import example.discovery.service.GreetingService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class MixedController {

    private final GreetingService service;

    public MixedController(GreetingService service) {
        this.service = service;
    }

    @ResponseBody
    @GetMapping(path = "/text",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greetingText(
            @RequestParam(defaultValue = "An") String name) {
        return service.greet(name);
    }

    @GetMapping(path = "/headers",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> greetingWithHeader() {
        return ResponseEntity.ok()
                .header("X-Source", "controller")
                .body("Kết quả từ ResponseEntity");
    }
}
~~~

Hai method trong class @Controller **không đi qua template**: /text có @ResponseBody, /headers trả ResponseEntity. Đây là bằng chứng @Controller không bị giới hạn ở HTML.

### 7.6. Chạy và kiểm tra từng endpoint

Tại thư mục gốc dự án Spring Initializr (nơi có pom.xml), chạy:

~~~bash
# macOS/Linux
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Server MVC mặc định thường nghe tại **http://localhost:8080**, trừ khi dự án thay đổi server.port. Mở terminal khác:

**A. HTML view**

~~~bash
curl -i "http://localhost:8080/greeting?name=Lan"
~~~

Kỳ vọng status **200**, Content-Type tương ứng HTML và body chứa:

~~~html
<h1>Xin chào, Lan!</h1>
~~~

HTML thực tế có thêm phần head/body và whitespace do template; trên đây là **đoạn quan trọng cần kiểm tra**, không phải toàn bộ response byte-for-byte.

**B. JSON API**

~~~bash
curl -i -H "Accept: application/json" \
  "http://localhost:8080/api/greetings/Lan"
~~~

Body JSON dự kiến (về mặt nội dung):

~~~json
{"message":"Xin chào, Lan!"}
~~~

Nếu JSON serializer escape các ký tự Unicode, những chuỗi JSON khác nhau về cách escape có thể biểu diễn **cùng giá trị message**.

**C. POST JSON**

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"name":"Minh"}'
~~~

Kỳ vọng status **201 Created** và JSON body:

~~~json
{"message":"Xin chào, Minh!"}
~~~

Nếu đặt Content-Type: text/plain trong khi mapping chỉ consumes JSON, Spring MVC thường trả **415 Unsupported Media Type**. Nếu gửi JSON sai cú pháp, có thể trả **400 Bad Request**. Đừng nhầm việc nhận body JSON qua @RequestBody với việc class được gắn @RestController.

**D. Văn bản từ @Controller + @ResponseBody**

~~~bash
curl -i -H "Accept: text/plain" \
  "http://localhost:8080/text?name=Mai"
~~~

Body dự kiến:

~~~text
Xin chào, Mai!
~~~

Đây **không phải view name**, nhờ @ResponseBody.

**E. ResponseEntity từ @Controller**

~~~bash
curl -i "http://localhost:8080/headers"
~~~

Kỳ vọng status **200**, response header:

~~~http
X-Source: controller
~~~

Và body:

~~~text
Kết quả từ ResponseEntity
~~~

Nếu làm ví dụ trên Windows PowerShell cũ, có thể dùng **curl.exe** thay vì alias curl để chắc chắn gọi công cụ curl thật. Khi chạy đồng thời nhiều demo Spring Boot, hãy chắc chắn cổng 8080 chưa bị chiếm.

## 8. Khi component scan không thấy controller: một thí nghiệm

Từ project trên, nếu chuyển DiscoveryApplication.java sang package **example.discovery.bootstrap** mà vẫn giữ controller ở **example.discovery.web**, cấu trúc thành:

~~~text
example.discovery.bootstrap.DiscoveryApplication
example.discovery.web.PageController
example.discovery.web.GreetingRestController
example.discovery.web.MixedController
example.discovery.service.GreetingService
~~~

Chỉ thay package/đường dẫn của lớp main mà không đổi vùng scan, mặc định Boot quét **example.discovery.bootstrap** và các subpackages. Các bean sibling **web** và **service** không thuộc phạm vi ấy. Ứng dụng có thể khởi động nhưng không có các endpoint mong đợi; request GET /api/greetings/Lan hoặc /greeting thường trả **404**.

**Cách khắc phục:** đưa lớp main về package **example.discovery**. Đây là cấu trúc đơn giản và thường nên ưu tiên.

Một phương án tùy hoàn cảnh là khai báo:

~~~java
@SpringBootApplication(scanBasePackages = "example.discovery")
public class DiscoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryApplication.class, args);
    }
}
~~~

Đây là **phiên bản thay thế của lớp main**, không được đồng thời tạo hai DiscoveryApplication. Annotation parameter giải quyết phạm vi component scan cho ví dụ; trong dự án có JPA entity hoặc Spring Data repositories, có thể cần xét riêng phạm vi @EntityScan/@EnableJpaRepositories và cấu trúc package.

### Một số lý do khác khiến không tìm thấy controller

- Class không có @Controller/@RestController hoặc custom annotation meta-annotated phù hợp.
- Controller được đánh dấu stereotype đúng nhưng không phải bean trong **DispatcherServlet ApplicationContext** đang xử lý request.
- @ComponentScan có **excludeFilters**, hoặc **useDefaultFilters=false** khiến class bị loại.
- Bean đăng ký có điều kiện **@Profile**, **@Conditional...** chưa thỏa.
- Controller không được đưa vào runtime classpath/artifact, hoặc đã biên dịch code cũ.
- Có nhiều DispatcherServlet hoặc nhiều ApplicationContexts, controller nằm trong context không nhìn thấy từ servlet cần phục vụ request.
- Handler method thiếu @RequestMapping hoặc composed HTTP mapping, nên bean controller không cung cấp endpoint.
- URL bạn gọi sai context path, servlet mapping, prefix @RequestMapping, HTTP method, hoặc bị filter/security/proxy chặn trước khi đến MVC.

**Chẩn đoán theo tầng:** đầu tiên xác định bean tồn tại hay không, sau đó xác định mapping được đăng ký hay không, cuối cùng mới đối chiếu HTTP request thực tế.

## 9. Từ controller được phát hiện đến mapping chính xác

**Bean được nhận diện và endpoint được định tuyến là hai công việc khác nhau.** Sau khi Spring tìm thấy controller, `RequestMappingHandlerMapping` đăng ký metadata của các method. Prefix ở class như `@RequestMapping("/api/books")` kết hợp với `@GetMapping("/{id}")` thành `GET /api/books/{id}`; `@PostMapping` tại class đó có thể cùng dùng path `/api/books` nhưng khác HTTP method.

Controller mẫu ở phần 7 đã cho thấy GET với URI variable, POST nhận JSON, response status và media type. Khi ứng dụng chạy, nên kiểm tra thêm các tình huống sau:

| Dấu hiệu | Câu hỏi tiếp theo |
| --- | --- |
| HTTP 404 | Bean/controller có được scan, method có mapping và URL có đúng prefix/context path không? Một handler cũng có thể chủ động trả 404 cho tài nguyên không tồn tại. |
| HTTP 405 | Path đã có handler nhưng request sử dụng sai HTTP method? |
| HTTP 406 | Header `Accept` có phù hợp với response `produces` và converter không? |
| HTTP 415 | Request `Content-Type` có phù hợp `consumes` và converter đọc body không? |
| Startup báo `Ambiguous mapping` | Có hai handler đăng ký cùng điều kiện method/path/params/headers/media type không? |

Một bean controller có thể có nhiều handler method, hoặc không có mapping nào. Trùng mapping không được sửa chỉ bằng cách đổi tên phương thức Java: cần thay điều kiện HTTP theo hợp đồng API. Đối với việc so sánh nhiều mẫu URI cạnh tranh, hãy dựa vào độ cụ thể của mapping chứ không dựa vào thứ tự khai báo.

Phần này chỉ nối quá trình **controller discovery** với routing. Các bài tiếp theo trong chương đi sâu riêng vào mapping mức class/method, tổ hợp điều kiện, URI patterns, ambiguity và mã lỗi; không cần lặp lại cùng một ứng dụng minh họa ở mỗi mức khái niệm.

## 10. MVC annotation controller khác gì Servlet hoặc functional endpoint?

Spring MVC vẫn có thể viết HTTP Servlet theo cách thấp hơn, tự đăng ký Servlet hoặc sử dụng functional endpoint **RouterFunction**. Vì vậy “ứng dụng Spring Web có endpoint” không đồng nghĩa mọi endpoint đều nằm trong @Controller.

| Kiểu HTTP handler | Cách đăng ký | Spring MVC RequestMappingHandlerMapping có quản lý như annotated controller? |
|---|---|---|
| @Controller + @GetMapping | Bean controller + annotation mapping | Có |
| @RestController + @GetMapping | Bean controller + annotation mapping | Có |
| Một @Service có @GetMapping | Bean service nhưng không mang stereotype controller | Không, chỉ vì @GetMapping thì chưa đủ |
| Servlet riêng | Servlet registration/mapping | Không phải annotated controller mapping |
| Spring MVC functional RouterFunction | RouterFunction bean | Đi qua functional routing infrastructure, không phải @GetMapping |
| Spring WebFlux annotated controller | Reactive application context + reactive mapping | Dùng WebFlux infrastructure, không phải MVC DispatcherServlet |
| Spring WebFlux functional route | RouterFunction<ServerResponse> WebFlux | Đi qua WebFlux functional routing |

**Đặc biệt:** @RestController không có nghĩa “dùng Spring WebFlux”. Nó hoạt động trong cả **Spring MVC** và **Spring WebFlux**, tùy dependency, ApplicationContext và web stack đang kích hoạt. Để biết server thật dùng Servlet hay reactive, hãy kiểm tra runtime và cấu hình thực tế.

## 11. Vòng đời bean, Dependency Injection và kiến trúc controller

Vì controller là **Spring bean**, nó tham gia Dependency Injection, scope, lifecycle và có thể chịu tác động của các BeanPostProcessor.

Trong ví dụ runnable, cả PageController và GreetingRestController đều nhận GreetingService qua **constructor injection**. Spring giải quyết một bean GreetingService và tiêm vào controller. Nếu không có bean tương thích, việc tạo context thường thất bại với lỗi dependency injection thay vì âm thầm tạo endpoint thiếu nghiệp vụ.

### Vì sao constructor injection là lựa chọn tốt?

- Dependency được xác định rõ ngay trong constructor.
- Dễ tạo controller trong unit test bằng service fake.
- Field có thể final, tránh trạng thái chưa khởi tạo.
- Không cần dựa vào field injection và runtime reflection để cài từng field.

### Thread-safety và scope

Controller beans mặc định thường là **singleton**. Nhiều request có thể gọi **cùng một controller instance**, đồng thời trên nhiều thread (đối với MVC/Servlet).

**Lỗi không nên viết:**

~~~java
@RestController
class UnsafeController {

    private String currentName;

    @GetMapping("/unsafe")
    public String unsafe(@RequestParam String name) {
        currentName = name;
        return currentName;
    }
}
~~~

Đây là **minh họa lỗi concurrent state**, có thể gây request nọ trả giá trị của request kia. Controller không nên chứa mutable request-specific fields. Dữ liệu request nên lưu trong **biến cục bộ**, method parameters hoặc cơ chế scope/context được quản lý đúng.

Controller singleton không ngăn service có trạng thái độc lập, nhưng service cũng phải được thiết kế thread-safe nếu là singleton. @RestController không làm ứng dụng tự an toàn luồng.

### Validation và phân tầng

Controller chịu trách nhiệm **chuyển giao HTTP**: đọc path/query/body, áp dụng validation phù hợp, gọi service, lựa chọn status/response. Nghiệp vụ và giao dịch thường đặt ở service. Không dồn việc truy vấn database, gửi email, nhiều chiến lược xử lý dài vào controller nếu có thể tách thành thành phần chuyên trách.

Một API production thường bổ sung:

- DTO đầu vào/đầu ra và validation (@Valid cùng provider tương thích).
- @ControllerAdvice/@RestControllerAdvice để chuẩn hóa xử lý lỗi.
- Authentication/authorization trong filter/security chain.
- Logging/tracing, giới hạn payload và timeout.
- Tests cho mapping, content types và status codes.

**@ControllerAdvice không phải controller endpoint thông thường.** Nó giúp áp dụng exception handlers, binder/model methods cho phạm vi controller phù hợp. **@RestControllerAdvice** tương đương @ControllerAdvice có semantics @ResponseBody cho exception response handlers, không tự tạo một REST route vì có chữ RestController trong tên annotation.

## 12. Custom stereotype và cách Spring nhận diện qua meta-annotation

Do @Controller là stereotype được meta-annotated với @Component, một annotation riêng có thể biểu đạt ý đồ dự án bằng cách meta-annotate:

~~~java
package example.discovery.web;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.stereotype.Controller;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Controller
public @interface WebPage {
}
~~~

Đây là một **annotation Java hoàn chỉnh** (file **WebPage.java**), được Spring nhận diện là controller stereotype nếu component scanning và metadata xử lý theo cấu hình phù hợp.

Dùng:

~~~java
@WebPage
public class WelcomePageController {

    @GetMapping("/legacy-home")
    public String home() {
        return "greeting";
    }
}
~~~

Đoạn class là **ví dụ minh họa** cần import WebPage/@GetMapping, có view greeting và context MVC như phần trên.

**Điểm khác biệt:** custom stereotype mang **@Controller** thì thừa hưởng ý nghĩa controller; custom stereotype chỉ mang **@Component** mà không mang @Controller thường được scan thành bean nhưng **không đủ để được xem là annotated MVC controller**.

Khi tự tạo annotation mới, tránh nhân thêm layer trừu tượng không cần thiết cho dự án nhỏ. Nếu cần aliasing các thuộc tính annotation, phải xem **@AliasFor** và các yêu cầu khai báo meta-annotation ở phiên bản Spring tương ứng; không tùy ý đặt field rồi giả định nó sẽ được chuyển tiếp.

## 13. Proxy, context và những trường hợp controller khó phát hiện

### Controller bean bị bọc AOP proxy

Spring có thể dùng AOP proxy để triển khai transaction, security hay advice. Với controller có interface và proxy kiểu JDK, handler detection có thể không nhìn thấy annotations trên concrete class theo cách bạn tưởng. Tài liệu Spring khuyến nghị **class-based proxying** cho controller khi cần AOP proxy.

Không nên tự khắc phục bằng cách thêm @RestController lên từng method hoặc đặt controller mapping lên service. Xác định **kiểu proxy thực tế**, vị trí annotation, cấu hình AOP và version framework; khi cần có thể cấu hình class-based proxy phù hợp. Với Spring 6+, interface annotation/proxy cần đối chiếu Javadoc đúng phiên bản.

### Root context và DispatcherServlet context

Một ứng dụng Servlet truyền thống có thể tạo:

~~~text
Root WebApplicationContext:
   Service, Repository, security-related infrastructure...
      |
      | parent được child tham chiếu
      v
DispatcherServlet child WebApplicationContext:
   Controller, HandlerMapping, HandlerAdapter, ViewResolver...
~~~

**Child context có thể nhìn thấy bean trong parent**; parent không tự thấy bean chỉ tồn tại ở child. Trong Spring MVC truyền thống, controller thường đặt trong context của DispatcherServlet tương ứng. Nếu tạo nhiều DispatcherServlet, mỗi servlet có thể có mappings và controller context riêng.

Một ví dụ lỗi thiết kế là scan controller vào một context không được servlet phục vụ rồi cho rằng cứ có ApplicationContext trong JVM là HTTP request sẽ tìm thấy controller. Phải kiểm tra **bean visibility và hạ tầng HandlerMapping của đúng servlet**.

### Lazy initialization và profile

Nếu một controller bị ràng buộc **@Profile("admin")**, bean có thể chỉ tồn tại khi profile admin được kích hoạt. Nếu bean chưa được định nghĩa vì profile/condition không thỏa, Spring MVC không thể đăng ký handler cho nó. Với lazy initialization, đừng suy từ việc constructor đã chạy hay chưa mà kết luận mapping có tồn tại; hãy kiểm tra bean definitions/mapping registry phù hợp.

### Controller nằm ngoài dependency runtime

Maven/Gradle có thể compile class nhưng không đưa nó vào artifact đang chạy do sai module dependency hoặc packaging. Đọc đúng classpath, log startup và artifact/version được triển khai, nhất là trong hệ thống nhiều module. Java source trong editor không đồng nghĩa class đó đang tồn tại trong tiến trình web server.

## 14. Cách chẩn đoán controller không được phát hiện

Đi từ **đúng ứng dụng → đúng bean → đúng mapping → đúng HTTP request**:

### Bước 1 — Xác nhận đúng tiến trình và web stack

- Đúng cổng **server.port** và đúng context path chưa?
- Đúng instance/environment đang chạy? Có reverse proxy, Docker port mapping hoặc gateway đổi đường dẫn không?
- Dự án là **Spring MVC Servlet** hay **Spring WebFlux reactive**?
- Logs có cho thấy embedded server khởi động thành công không?

### Bước 2 — Xác nhận controller là Spring bean

- Có @Controller/@RestController hoặc custom annotation meta-annotated @Controller không?
- Class có nằm dưới package @SpringBootApplication hoặc các @ComponentScan tương ứng?
- Có filters, @Profile, @Conditional nào khiến bean bị loại?
- Có lỗi tạo bean do dependency injection? Nếu startup failed, đừng chỉ truy 404.
- Nếu không dùng Boot, XML/Java configuration đã scan hoặc đăng ký controller trong web context thích hợp chưa?

### Bước 3 — Xác nhận RequestMappingHandlerMapping đã đăng ký handler

- Method có @GetMapping/@PostMapping/@RequestMapping không?
- URL class-level @RequestMapping và method-level có ghép đúng?
- Có mapping trùng, class proxy hoặc interface annotation gây khó nhận diện không?
- Servlet nào sở hữu mapping này? Có nhiều ApplicationContexts không?
- Có auto-configuration/scan khác đã tạo bean nhưng MVC infrastructure chưa bật đúng cách không?

Trong môi trường phát triển, nếu bật **Spring Boot Actuator** và expose endpoint **mappings** một cách có kiểm soát, có thể kiểm tra mappings đã đăng ký. Cẩn trọng vì endpoint quản trị có thể chứa thông tin chi tiết ứng dụng; không mở công khai không kiểm soát. Không bắt buộc dùng Actuator nếu có startup log và application context inspection phù hợp.

### Bước 4 — Kiểm tra HTTP request thực tế

~~~bash
curl -i -v -H "Accept: application/json" \
  "http://localhost:8080/api/greetings/Lan"
~~~

Xem:

- Path, query string, method và base path.
- Content-Type cho request có body; Accept cho response cần nhận.
- Authentication, proxy, CORS, redirect và filters.
- **404** do route không tồn tại khác với **405** sai HTTP method, **406** media type response không đáp ứng, **415** request media type không được hỗ trợ.

Browser devtools hoặc Postman/curl hữu ích hơn đoán dựa trên URL trong code. Nếu có Spring Security, một endpoint hợp lệ có thể trả **401/403** trước khi controller được gọi.

### Bước 5 — Đọc logs đúng điểm

Một số dấu hiệu:

| Dấu hiệu | Nguyên nhân đáng kiểm tra |
|---|---|
| Ứng dụng Boot đã khởi động nhưng controller mới 404 | Package scan, profile/condition, URL, mapping chưa đăng ký |
| Startup báo **Ambiguous mapping** | Hai handler có điều kiện đăng ký không thể phân biệt |
| 404 chỉ với đường dẫn có tiền tố | Context path, servlet path hoặc class-level @RequestMapping |
| 405 cho URL tương tự | HTTP method khác handler mapping |
| API trả chữ **greeting** thay vì HTML | Có thể đổi @Controller thành @RestController khiến String thành body |
| MVC cố tìm template với tên **ok** | @Controller trả String view name khi người viết muốn body "ok" |
| JSON serialization thất bại | Converter/dependency, DTO serialization, kiểu return |
| Controller cần service nhưng context không startup | Missing bean, circular dependency, constructor injection/configuration |
| Endpoint biến mất chỉ ở profile production | Conditional registration, packaging, @Profile, config khác |
| Chỉ một DispatcherServlet nhận được controller | Sai hoặc khác biệt giữa child contexts và servlet mappings |

## 15. Kiểm chứng bằng test và quan sát cấu hình

Việc kiểm thử có thể chia thành ba lớp:

1. **Unit test của service/controller:** gọi Java method để kiểm tra nghiệp vụ. Không chứng minh URL mapping, scan hoặc converter hoạt động.
2. **MVC slice test:** @WebMvcTest với MockMvc trong ứng dụng Boot MVC; thường giới hạn context vào lớp web, cần import/mock service và các custom configurations phù hợp. Không được kết luận toàn app scan đúng chỉ từ slice test.
3. **Integration test với full context:** @SpringBootTest kết hợp MockMvc hoặc cổng HTTP thực để xác nhận component scan, handler mappings, converters, filters theo setup thực tế.

Ví dụ hành vi muốn test cho project ở phần 7:

- GET /greeting?name=Lan trả **HTML** và trong body có **Xin chào, Lan!**.
- GET /api/greetings/Lan với Accept: application/json trả JSON có **message**.
- POST /api/greetings với Content-Type: application/json và body hợp lệ trả **201**.
- GET /text?name=Mai trả **text/plain**; không cố tìm view tên câu chào.
- GET /headers có **X-Source: controller** ngay cả khi class dùng @Controller.
- Request sai method/media type phản hồi theo contract.
- Thử chuyển controller ra ngoài scan scope trong **môi trường kiểm thử riêng** thì mapping tương ứng phải không còn xuất hiện.

Trong test và môi trường production, cần tránh phụ thuộc vào chuỗi toàn bộ HTML/JSON có whitespace/order cố định khi không cần thiết. Kiểm tra **status, header, JSON field, một số HTML element quan trọng**, và những side effects nghiệp vụ thật sự.

## 16. Những nhầm lẫn thường gặp

**1. “@RestController tự tạo REST server.”** Không. Nó chỉ mô tả controller và @ResponseBody semantics. Server/DispatcherServlet hoặc WebFlux runtime được cấu hình riêng.

**2. “@Controller chỉ dành cho trang HTML.”** Không. @Controller có thể dùng @ResponseBody, ResponseEntity để trả body JSON/text.

**3. “@RestController + @GetMapping vẫn render template khi trả String.”** Không theo cách thông thường: String là response body, không phải logical view name.

**4. “Bất kỳ @Component nào có @GetMapping đều tạo endpoint.”** Không. MVC annotated handler detection tìm controller stereotype thích hợp.

**5. “@Controller có nghĩa chắc chắn đã được phát hiện.”** Không. Annotation không tự thêm class nằm ngoài component scan vào ApplicationContext.

**6. “Spring Boot tự scan toàn bộ Maven dependencies.”** Không. Mặc định scan từ package của @SpringBootApplication, ngoại lệ do explicit import/configuration/dependencies.

**7. “Đổi method name thì đổi URL.”** Không. URL được khai báo trong request mapping; method Java name chỉ là tên nội bộ (trừ các cơ chế configuration hiếm khác).

**8. “Mỗi @RestController chỉ có một endpoint.”** Không. Một bean có thể chứa nhiều handler methods.

**9. “@RequestMapping đủ cho mọi thứ, không cần xem HTTP method.”** @RequestMapping nếu không giới hạn method có semantics rộng; nên dùng shortcut annotation @GetMapping/@PostMapping tương ứng khi hợp đồng rõ ràng.

**10. “@RestController mặc nhiên trả application/json dù return String hay thiếu JSON converter.”** Không. Return type, converters và content negotiation quyết định body/media type.

**11. “Hai controller cùng URL thì framework luôn chọn class đầu tiên.”** Không. Mapping registry xem xét toàn bộ điều kiện; ambiguity có thể làm startup/request thất bại.

**12. “Controller singleton có thể lưu biến instance cho mỗi request.”** Nguy hiểm. Singleton bean có thể xử lý concurrent requests, tránh mutable request-specific state.

**13. “Dùng @ControllerAdvice là tự có URL mới.”** Không. Advice cung cấp xử lý chung, không tự tạo HTTP mapping.

**14. “Cần @EnableWebMvc trong mọi project Spring Boot để phát hiện @RestController.”** Không. Boot thường tự cấu hình MVC; thêm @EnableWebMvc có thể làm mất những mặc định của Boot.

**15. “@RestController chắc chắn là WebFlux.”** Không. MVC và WebFlux đều có annotated controller model; khác nhau ở web stack thực tế.

## 17. Tự kiểm tra và bài tập ứng dụng

**Câu 1:** Một class @Controller trả về String **"dashboard"** từ @GetMapping("/dashboard"), chuyện gì xảy ra?

**Đáp án:** Khi không có @ResponseBody hoặc return-value semantics đặc biệt khác, Spring MVC coi String là tên view **dashboard** và dùng view resolution. Nếu thiếu view/template thì có thể phát sinh lỗi render.

**Câu 2:** Cùng method trên nhưng class đổi thành @RestController?

**Đáp án:** Spring đưa chuỗi **dashboard** vào HTTP response body. Nó không tự render template dashboard.

**Câu 3:** Một class @Service chứa @GetMapping("/x") và được scan thành bean. GET /x có được map không?

**Đáp án:** Không chỉ nhờ @GetMapping. Annotated MVC handler detection yêu cầu controller stereotype hoặc handler configuration phù hợp.

**Câu 4:** Main class đặt trong example.app.bootstrap, controller trong example.app.web. Mặc định Boot có quét controller không?

**Đáp án:** Không nếu chỉ dùng scan mặc định từ package example.app.bootstrap; cần đặt main ở package cha example.app hoặc khai báo scan hợp lý.

**Câu 5:** Làm sao @Controller trả JSON mà không chuyển toàn class sang @RestController?

**Đáp án:** Thêm **@ResponseBody** vào handler cần trả body hoặc dùng **ResponseEntity<T>**.

**Câu 6:** @RestController có thể trả HTML không?

**Đáp án:** Có thể trả body có Content-Type text/html nếu endpoint chủ đích sinh HTML, nhưng return String của @RestController không được hiểu như view name; muốn server-side template view, @Controller phù hợp hơn.

**Câu 7:** Nếu đã có controller bean, chắc chắn URL được đăng ký chưa?

**Đáp án:** Chưa. MVC phải có infrastructure đúng context, nhận diện stereotype, tìm method mappings và đăng ký thành công.

**Câu 8:** Spring MVC quét toàn bộ classpath lại trên từng HTTP request?

**Đáp án:** Không. Mapping registry được xây trong quá trình khởi tạo và dùng khi dispatch request.

**Câu 9:** Vì sao controller chạy ở dev nhưng không có trong production?

**Đáp án:** Kiểm tra profiles, conditionals, package/classpath của artifact, deployment, context, web stack và URL/proxy trước khi sửa annotation.

**Câu 10:** Một @RestController dùng field String lastName để lưu query name, có an toàn không?

**Đáp án:** Thường không; controller mặc định singleton và có thể xử lý nhiều request đồng thời, cần giữ request state ở biến cục bộ hoặc mechanism đúng scope.

### Bài tập thực hành

Từ project chạy được ở phần 7, làm từng bước:

1. Thêm GET /api/greetings/default trả một GreetingResponse với thông điệp cố định, kiểm tra tương tác với pattern GET /api/greetings/{name}. Hãy quan sát mapping specificity thay vì đoán Spring luôn chọn một method.
2. Thêm @Controller method với @ResponseBody trả **text/plain**, kiểm chứng không tìm view resolver.
3. Đặt một controller mới ở package không thuộc scan, khởi động rồi quan sát mapping chưa có; chuyển về subpackage đúng và kiểm chứng.
4. Thử một endpoint cùng URL nhưng GET so với POST; xác nhận hai method HTTP được ánh xạ riêng.
5. Thêm handler có consumes=application/json, thử request Content-Type: text/plain và giải thích status.
6. Thêm Spring Security nếu chương trình học đã đề cập; xác định filter chain có thể chặn request trước MVC khi thiếu quyền, không nhầm đó là controller discovery error.

Không cần sửa code production để làm các thí nghiệm có tính phá cấu hình; dùng project học tập hoặc nhánh thử riêng.

## 18. Tài liệu chính thức

- [Spring Framework — Annotated Controllers: Declaration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html): @Controller, @RestController, component scanning và lưu ý AOP proxy.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): @RequestMapping, @GetMapping, điều kiện mapping và pattern.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): phân loại các kiểu trả về của handler.
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): ghi HTTP response body và message converters.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): điều khiển status, headers, body.
- [Spring Framework — Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): stereotype annotations, meta-annotation, filters.
- [Spring Framework — DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): request flow và context.
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): package gốc của @SpringBootApplication và phạm vi component scan.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC auto-configuration.
- [Spring Framework — Annotated Controllers in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann.html): cùng ý tưởng annotation trên reactive stack.

**Điểm cần ghi nhớ:** **@Controller** đánh dấu lớp là Spring MVC controller bean và cho phép xử lý view hoặc response tùy return type. **@RestController** thêm @ResponseBody semantics để trả HTTP body thuận tiện. **Controller discovery** cần cả đăng ký Spring bean trong đúng context lẫn **RequestMappingHandlerMapping** tìm/đăng ký handler methods. Khi thấy 404, hãy xác định lần lượt **đúng ứng dụng → bean có tồn tại → mapping có đăng ký → request có khớp**.
