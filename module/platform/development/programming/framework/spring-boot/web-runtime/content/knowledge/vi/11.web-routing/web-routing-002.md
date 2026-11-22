# @RequestMapping, HTTP method, consumes và produces

Khi một HTTP request đi vào ứng dụng Spring Boot, framework phải quyết định **controller method nào được gọi**. Quyết định không chỉ dựa vào URL: cùng một đường dẫn có thể được phục vụ khác nhau theo **HTTP method** (`GET`, `POST`, `PUT`...), **Content-Type của dữ liệu gửi lên** (`consumes`), **Accept của dữ liệu mong nhận** (`produces`), các query parameters và headers khác.

Trong Spring Framework, `@RequestMapping` mô tả các điều kiện định tuyến đó. Những annotation `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping` và `@DeleteMapping` là các shortcut giúp code diễn đạt HTTP method cụ thể. Trong Spring Boot, controller method chỉ được gọi khi request đáp ứng **đủ những điều kiện mapping có hiệu lực**.

Bài học này thuộc nhóm **Định tuyến web** và tập trung vào **`@RequestMapping`, HTTP method, `consumes`, `produces`**. Phần ví dụ chạy trên **Spring Boot 3.3.13, Spring MVC, Java 21 và Gradle**. Spring WebFlux cũng hỗ trợ mô hình annotated request mappings và các khái niệm `consumes`/`produces` tương ứng, nhưng runtime xử lý HTTP khác với Servlet MVC. Các ví dụ bên dưới chủ động dùng `spring-boot-starter-web` để minh họa Servlet/Spring MVC một cách rõ ràng.

## 1. Định tuyến là việc so khớp nhiều điều kiện

Request mapping có thể được hình dung như một tập điều kiện:

~~~text
HTTP request
    |
    v
Servlet container / DispatcherServlet
    |
    v
RequestMappingHandlerMapping
    |
    +-- Path khớp?                 /api/items/42
    +-- HTTP method khớp?          GET
    +-- Params khớp?               q, mode=summary...
    +-- Headers khớp?              X-Client=demo...
    +-- Consumes khớp?             Content-Type: application/json
    +-- Produces khớp?             Accept: application/json
    |
    +-- Chọn mapping phù hợp nhất
    |
    v
RequestMappingHandlerAdapter
    |
    v
Controller method + argument binding
    |
    v
Return value / message conversion / HTTP response
~~~

Đây là mô tả khái niệm, không phải thứ tự thuật toán cứng của mọi bước. Spring có cơ chế tìm và xếp hạng mapping ứng viên; nếu hai mapping tương đương đến mức framework không thể chọn duy nhất, có thể xảy ra lỗi **ambiguous mapping**.

Điểm quan trọng: **mapping là bước tìm handler**, còn `@RequestBody`, `@RequestParam`, `@PathVariable` là bước **đưa dữ liệu vào tham số method** sau khi mapping được chọn. `@ResponseBody` và message converter lại liên quan **ghi response**. Không nên trộn ba trách nhiệm này.

### 1.1. Cấu trúc annotation tổng quát

~~~java
@RequestMapping(
    path = "/api/items",
    method = RequestMethod.POST,
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ItemView create(@RequestBody CreateItemRequest request) {
    // ...
}
~~~

Đây là **code fragment** mô tả cú pháp; những kiểu `ItemView`, `CreateItemRequest` và phần thân method cần được định nghĩa trong ứng dụng. Ý nghĩa: handler chỉ nhận POST tới `/api/items` với loại body là JSON và có thể tạo biểu diễn JSON mà client chấp nhận.

Tương đương về điều kiện HTTP method:

~~~java
@PostMapping(
    path = "/api/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ItemView create(@RequestBody CreateItemRequest request) {
    // ...
}
~~~

Trong ứng dụng thật, chỉ dùng **một** trong hai annotation mapping trên cùng method, không chồng `@RequestMapping` với `@PostMapping`.

## 2. Sáu nhóm điều kiện của @RequestMapping

| Thuộc tính | Khớp với gì? | Ví dụ |
| --- | --- | --- |
| `path` / `value` | Đường dẫn URL của request | `"/api/items/{id}"` |
| `method` | HTTP request method | `RequestMethod.GET`, `RequestMethod.POST` |
| `params` | Điều kiện query/form parameters | `"q"`, `"mode=full"`, `"!debug"` |
| `headers` | Điều kiện HTTP headers | `"X-Client=demo"`, `"!X-Legacy"` |
| `consumes` | Media type của **request body** qua `Content-Type` | `"application/json"` |
| `produces` | Media type phản hồi mà client **chấp nhận** qua `Accept` | `"application/json"`, `"text/plain"` |

Các điều kiện hoạt động kết hợp: nếu mapping yêu cầu `POST` + `Content-Type: application/json` + `Accept: application/json`, một request chỉ thỏa URL nhưng gửi `text/plain` có thể không vào handler đó.

Trong một thuộc tính có nhiều lựa chọn, Spring hỗ trợ các biểu thức và quy tắc so khớp tương ứng. Ví dụ `consumes = {"application/json", "application/xml"}` cho phép **một trong hai media types**, không có nghĩa body đồng thời phải là cả JSON và XML. Với `params={"q","mode=full"}`, các điều kiện biểu thức phải cùng được đáp ứng.

### 2.1. path và value

`value` là alias của `path`. Hai cách sau biểu đạt cùng pattern:

~~~java
@GetMapping("/api/items/{id}")
@GetMapping(path = "/api/items/{id}")
~~~

Đây là hai cách viết thay thế, **không phải hai mapping cùng khai báo lên một method**.

Các pattern thường gặp:

- `/api/items`: một collection endpoint.
- `/api/items/{id}`: biến trong path được bind bằng `@PathVariable`.
- `/api/items/search`: đường dẫn tĩnh dành cho tìm kiếm.
- `/api/files/**`: pattern nhiều cấp phù hợp với path matching configuration.

Không nên suy luận mọi path matching đều phân biệt hoặc không phân biệt chữ hoa, dấu slash cuối, suffix extension giống nhau. Spring Framework 6 sử dụng PathPattern trong cấu hình mặc định phổ biến; cách xử lý trailing slash và những tùy chọn matcher có thể khác các ứng dụng Spring 5 trước đây.

### 2.2. Lớp controller và method

Khai báo class-level để dùng prefix chung:

~~~java
@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{id}")
    public ItemView get(@PathVariable long id) {
        // ...
    }

    @PostMapping
    public ItemView create(@RequestBody CreateItemRequest body) {
        // ...
    }
}
~~~

Đây là **skeleton**. Mapping hiệu lực lần lượt là `GET /api/items/{id}` và `POST /api/items`. Class-level prefix ghép với method-level path; đừng đọc `@GetMapping("/{id}")` thành endpoint ở root `/{id}`.

Với `consumes` và `produces`, **method-level declaration có thể ghi đè thay vì cộng dồn class-level declaration**. Đó là ngoại lệ quan trọng khi thiết kế API. Ví dụ class-level `produces="application/json"` nhưng một method khai báo `produces="text/plain"` thì method đó có thể trả plain text; không yêu cầu cùng lúc JSON và plain text. Đừng đặt class-level media restrictions nếu nhiều endpoints cố ý phục vụ các loại nội dung khác nhau.

## 3. HTTP method và tính đúng đắn của hợp đồng API

HTTP method là một phần của request routing. Nó truyền tải ý nghĩa giao thức, không chỉ là cú pháp:

| Method | Ý nghĩa thường dùng | Mapping annotation |
| --- | --- | --- |
| `GET` | Truy vấn biểu diễn tài nguyên, thông thường không làm thay đổi trạng thái server | `@GetMapping` |
| `HEAD` | Lấy metadata của GET mà không nhận response body | `@RequestMapping(method=HEAD)` nếu khai báo riêng |
| `POST` | Gửi dữ liệu để xử lý hoặc tạo tài nguyên | `@PostMapping` |
| `PUT` | Thay thế/thiết lập trạng thái tài nguyên theo URI | `@PutMapping` |
| `PATCH` | Cập nhật một phần tài nguyên | `@PatchMapping` |
| `DELETE` | Yêu cầu xóa tài nguyên | `@DeleteMapping` |
| `OPTIONS` | Hỏi các khả năng HTTP/communication options | `@RequestMapping(method=OPTIONS)` nếu cần customize |

**GET** nên an toàn (safe); **PUT** và **DELETE** được thiết kế có tính idempotent theo ngữ nghĩa HTTP khi thực thi đúng. POST không mặc định idempotent. Những tính chất này phụ thuộc logic endpoint, không tự được bảo đảm chỉ nhờ annotation.

### 3.1. @RequestMapping không có method

Nếu viết:

~~~java
@RequestMapping("/api/ping")
public String ping() {
    return "pong";
}
~~~

thì mapping **không tự bị giới hạn chỉ GET**. Nó có thể nhận nhiều HTTP methods (với các điều kiện khác phù hợp), không nhất thiết là điều mong muốn cho public API.

Nên viết:

~~~java
@GetMapping("/api/ping")
public String ping() {
    return "pong";
}
~~~

Khi method nằm trong `@RestController`, chuỗi trả về được viết làm response body. Nếu method nằm trong `@Controller` không có `@ResponseBody`, cùng chuỗi có thể được hiểu như tên view; đây là **xử lý return value**, không phải điều kiện mapping.

### 3.2. HEAD và OPTIONS

Spring MVC có thể cung cấp hành vi tự động hỗ trợ **HEAD** cho GET mappings và xử lý **OPTIONS** dựa trên các methods được mapping, tùy thiết lập và handler. Khi phát triển API, hãy kiểm tra bằng client thật và test, không giả định toàn bộ status/headers chỉ từ việc nhìn tên @GetMapping.

HTTP method không được hỗ trợ cho một path có thể dẫn đến **405 Method Not Allowed** và header `Allow` phù hợp. Cần phân biệt **path không tồn tại (404)** với **path có mapping nhưng sai method (405)**.

### 3.3. Tránh dùng method như cơ chế phân quyền

`@PostMapping` không có nghĩa endpoint đã được bảo vệ; GET cũng không mặc nhiên công khai. Authentication, authorization và CSRF là trách nhiệm cấu hình security. Đừng dùng việc “chỉ nhận POST” như biện pháp bảo vệ thay cho Spring Security, policy và xác minh input.

## 4. consumes: giới hạn Content-Type của request

`consumes` trả lời câu hỏi:

> Handler này được phép nhận request body ở định dạng nào?

Ví dụ:

~~~java
@PostMapping(
    path = "/api/items",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ItemView create(@RequestBody CreateItemRequest body) {
    // ...
}
~~~

Client gọi:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json

{"name":"Notebook"}
~~~

thì mapping có thể khớp `consumes` và converter JSON được dùng để đọc body thành Java object.

Nếu client gửi:

~~~http
POST /api/items HTTP/1.1
Content-Type: text/plain

Notebook
~~~

thì với endpoint chỉ nhận JSON, kết quả có thể là **415 Unsupported Media Type**. Trong nhiều trường hợp, request bị từ chối **trước khi controller method chạy**.

### 4.1. consumes dùng Content-Type, không dùng Accept

Một nhầm lẫn phổ biến:

- `Content-Type: application/json` nói **request body đang chứa JSON**.
- `Accept: application/json` nói **client muốn response JSON**.

Gửi đúng `Accept` nhưng sai `Content-Type` vẫn không thỏa một endpoint `consumes=application/json`. Ngược lại, gửi JSON hợp lệ nhưng `Accept: application/xml` có thể bị từ chối ở phía `produces` nếu endpoint chỉ tạo JSON.

### 4.2. Các media types

| Media type | Dữ liệu gửi lên thường gặp |
| --- | --- |
| `application/json` | JSON body |
| `application/xml` | XML body, cần converter và dependency phù hợp |
| `text/plain` | Chuỗi text |
| `application/x-www-form-urlencoded` | Form fields mã hóa theo URL |
| `multipart/form-data` | Upload form đa phần, thường dùng `@RequestPart`/`MultipartFile` với MVC |
| `application/octet-stream` | Dữ liệu nhị phân tổng quát |

**Khai báo consumes không tự cài parser/codec.** `consumes="application/xml"` chỉ đặt điều kiện mapping; để bind XML thành object cần message converter phù hợp trên classpath và cấu hình. Tương tự, JSON cần converter đúng, record/DTO có hình dạng mà converter đọc được.

### 4.3. Nhiều consumes options và media type parameters

Có thể viết:

~~~java
@PostMapping(
    path = "/api/import",
    consumes = {"application/json", "text/plain"}
)
~~~

Đây là **annotation fragment**, cho phép một trong hai loại request. Controller vẫn phải thiết kế tham số phù hợp hoặc chọn các method riêng, tránh chỉ nhìn mapping mà bỏ qua binding.

`application/json;charset=UTF-8` thông thường tương thích với media type `application/json` khi tham số charset không bị ràng buộc cụ thể trong mapping. Nếu bạn tự khai báo parameter trong media type condition, giá trị phải phù hợp theo quy tắc matching; đừng dùng chuỗi charset ràng buộc quá mức nếu không có yêu cầu.

### 4.4. Consumes không có nghĩa request nhất định phải chứa body

`consumes` là điều kiện theo request media type, không phải annotation bắt buộc có body. `@RequestBody(required=true)` (mặc định) mới liên quan trực tiếp tới yêu cầu phải đọc được body ở bước binding. Một request có Content-Type đúng nhưng body rỗng vẫn có thể bị từ chối ở giai đoạn đọc tham số.

Không áp `consumes="application/json"` lên mọi GET một cách máy móc: nhiều GET không có request body và không gửi Content-Type. Điều đó có thể làm mapping fail không cần thiết.

## 5. produces: giới hạn media type response theo Accept

`produces` trả lời câu hỏi:

> Endpoint này có thể cung cấp representation nào cho client?

Ví dụ:

~~~java
@GetMapping(
    path = "/api/items/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ItemView find(@PathVariable long id) {
    // ...
}
~~~

Nếu request có `Accept: application/json`, mapping phù hợp. Nếu chỉ chấp nhận `text/plain` mà endpoint chỉ sản xuất JSON, server có thể trả **406 Not Acceptable**.

Khác với `consumes`, `produces` **không tự quyết định cách đọc request body**; nó là điều kiện cho representation mà client nhận.

### 5.1. Accept vắng mặt hoặc */*

Nhiều HTTP clients gửi `Accept: */*` hoặc không gửi Accept; điều này có nghĩa client không giới hạn chặt representation. Khi chỉ có một handler JSON, Spring thường có thể trả JSON theo khả năng converter.

Nếu có **hai methods cùng path và method nhưng khác produces**, một request `Accept: */*` có thể khiến lựa chọn không rõ ràng; hãy thiết kế content negotiation hoặc behavior mặc định có chủ đích và kiểm thử. Không dựa vào thứ tự phương thức trong file Java để chọn endpoint mặc định.

### 5.2. Accept với q-value

Một client có thể đưa mức ưu tiên:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.1
~~~

Spring sử dụng quy tắc media type matching và lựa chọn phù hợp. `q` là mức ưu tiên của client, không phải xác suất và không tự cài bất kỳ converter nào. Vẫn cần writer có thể tạo dạng được chọn.

### 5.3. produces không thay thế @ResponseBody

`produces="application/json"` không tự biến một `String` từ `@Controller` thành JSON. Cách framework diễn giải return value còn phụ thuộc `@ResponseBody`, `@RestController`, `ResponseEntity` hoặc view mechanism.

Ví dụ:

~~~java
@RestController
class MessageController {
    @GetMapping(path = "/message", produces = "text/plain")
    public String message() {
        return "hello";
    }
}
~~~

Đây là **đoạn class minh họa** có thể nằm trong một ứng dụng Spring Boot đã cấu hình; `@RestController` đảm bảo String là response body và `text/plain` là representation được chỉ định.

## 6. Routing media type và message conversion là hai bước khác nhau

Cần hiểu hai giai đoạn:

~~~text
Giai đoạn A: Request mapping
    POST /api/items
    Content-Type: application/json
    Accept: application/json
        |
        +-- @PostMapping(consumes="application/json",
                         produces="application/json")
                         có match không?
        |
        v
Giai đoạn B: Invoke controller và convert dữ liệu
    JSON -> @RequestBody CreateItemRequest
    controller business logic
    ItemView -> JSON response body
~~~

Ngay cả khi mapping khớp, request có thể lỗi ở giai đoạn convert:

- JSON không hợp lệ → có thể trả **400 Bad Request**.
- Body hợp lệ về JSON nhưng thiếu field bắt buộc theo validation → có thể trả **400** nếu validation được kích hoạt/cấu hình đúng.
- Kiểu body/DTO không thể chuyển đổi → lỗi đọc body, không giống lỗi URL.
- Controller ném exception → có thể trả 4xx/5xx tùy exception handler.
- Converter không thể ghi dạng response phù hợp → có thể xảy ra lỗi chuyển đổi hoặc content negotiation.

Trong **Spring MVC**, các bộ đọc/ghi kiểu này thường đi qua `HttpMessageConverter` (Jackson JSON, String converter...). Trong **Spring WebFlux**, khái niệm tương tự dùng `HttpMessageReader` và `HttpMessageWriter` trong reactive pipeline. Cùng annotation mapping không có nghĩa cùng runtime.

### 6.1. Khi nào thêm validation?

Spring Boot 3.x thường cần thêm:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

nếu muốn dùng Jakarta Bean Validation như `@NotBlank` hoặc `@Valid`. Không giả định chỉ có `spring-boot-starter-web` là mọi constraint annotation tự được áp dụng.

## 7. Kết hợp nhiều điều kiện trong @RequestMapping

Một handler có thể đồng thời yêu cầu path, method, params, headers và media types:

~~~java
@RequestMapping(
    path = "/api/reports",
    method = RequestMethod.POST,
    params = "mode=summary",
    headers = "X-Client=internal",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ReportView summarize(@RequestBody ReportInput input) {
    // ...
}
~~~

Đây là đoạn cú pháp minh họa; ``ReportInput`` và ``ReportView`` là kiểu ứng dụng tự định nghĩa, không phải class có sẵn trong Spring.

Request phải đáp ứng:

1. Path `/api/reports`.
2. HTTP method POST.
3. Query/form parameter `mode` có giá trị `summary`.
4. Header `X-Client` có giá trị `internal`.
5. Content-Type request là application/json.
6. Accept cho phép application/json.

Nếu một điều kiện không thỏa, method không phải lựa chọn hợp lệ. Status lỗi cụ thể có thể khác tùy điều kiện thất bại, các mappings khác, error handling và cấu hình.

### 7.1. params: có mặt, không có mặt, bằng giá trị

~~~java
@GetMapping(path = "/search", params = "q")
@GetMapping(path = "/search", params = "!q")
@GetMapping(path = "/search", params = "mode=full")
@GetMapping(path = "/search", params = "mode!=full")
~~~

Đây là **bốn annotation ví dụ độc lập**, không đặt cả bốn lên cùng method. Chúng lần lượt chỉ yêu cầu `q` có mặt, `q` vắng mặt, `mode=full`, hoặc `mode` khác `full` theo ngữ nghĩa expression.

Nếu chỉ muốn `q` có thể có/không có, thường đơn giản hơn dùng `@RequestParam(required=false)` hoặc `Optional<String>` trên **một** handler thay vì tạo nhiều mappings dễ va chạm.

### 7.2. headers và media type

~~~java
@GetMapping(path = "/partner", headers = "X-Client=demo")
~~~

đòi request có header `X-Client` giá trị `demo`.

Spring khuyến nghị dùng `consumes` thay vì cố mô tả Content-Type trong `headers`, và `produces` thay vì mô tả Accept trong `headers`. Hai thuộc tính media type có quy tắc đối chiếu và content negotiation chuyên biệt.

### 7.3. Một URL có thể phục vụ nhiều endpoints

Cùng `/api/echo` có thể nhận:

- POST JSON → handler nhận DTO từ `@RequestBody`.
- POST URL-encoded form → handler nhận `@RequestParam`.
- GET → endpoint đọc dữ liệu hoặc trả hướng dẫn.

Đây không phải ambiguous mapping nếu các conditions phân biệt được. Ngược lại, hai `@PostMapping(path="/api/echo",consumes="application/json")` có cùng điều kiện thường xung đột; thay tên method Java không làm điều kiện URL khác đi.

## 8. Ví dụ chạy được: Spring Boot 3.3 + Java 21 + Gradle

Chúng ta xây dựng REST API minh họa:

- `@GetMapping` theo ID.
- Cùng `GET /representation` trả JSON hoặc text theo `Accept`.
- Cùng `POST /echo` nhận JSON hoặc URL-encoded form theo `Content-Type`.
- `@RequestMapping(method = PUT)` nhận text/plain.
- `params` và `headers` để minh họa điều kiện bổ sung.
- Test lỗi 404, 405, 406, 415 bằng MockMvc.

Project có cấu trúc:

~~~text
routing-media-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/routing/
    │   ├── RoutingDemoApplication.java
    │   └── CatalogController.java
    └── test/java/com/example/routing/
        └── CatalogControllerTest.java
~~~

### 8.1. Cấu hình Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'routing-media-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dependency starter-web cung cấp Spring MVC, Jackson JSON trong cấu hình starter mặc định và embedded Tomcat. Starter test hỗ trợ JUnit 5 và MockMvc; không phải tự cài Tomcat riêng để chạy ví dụ.

### 8.2. Lớp Spring Boot main

**src/main/java/com/example/routing/RoutingDemoApplication.java**

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingDemoApplication.class, args);
    }
}
~~~

Vị trí package của main là cha cùng controller; Spring component scanning tìm thấy `CatalogController`.

### 8.3. Controller hoàn chỉnh

**src/main/java/com/example/routing/CatalogController.java**

~~~java
package com.example.routing;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    public record Item(long id, String name) {
    }

    public record CreateItemRequest(String name) {
    }

    @GetMapping(path = "/items/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> find(@PathVariable long id) {
        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(1L, "Notebook"));
    }

    @GetMapping(path = "/representation",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> representationJson() {
        return Map.of("message", "hello");
    }

    @GetMapping(path = "/representation",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String representationText() {
        return "hello";
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> echoJson(
            @RequestBody CreateItemRequest request) {
        if (request.name() == null || request.name().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "name must not be blank");
        }
        return Map.of("source", "json", "name", request.name());
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> echoForm(@RequestParam String name) {
        if (name.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "name must not be blank");
        }
        return Map.of("source", "form", "name", name);
    }

    @RequestMapping(path = "/manual",
            method = RequestMethod.PUT,
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String manual(@RequestBody String body) {
        return "received:" + body;
    }

    @GetMapping(path = "/search", params = "q",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> search(@RequestParam String q) {
        return Map.of("query", q);
    }

    @GetMapping(path = "/partner", headers = "X-Client=demo",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> partner() {
        return Map.of("access", "demo");
    }
}
~~~

**Cách đọc:**

- Class-level path `/api/catalog` là prefix cho mọi endpoint.
- `find` chỉ có GET, trả JSON và tự xác định 404 nếu ID khác 1.
- Hai method `representationJson` và `representationText` có cùng URL + method nhưng khác `produces`; chọn bằng `Accept`.
- Hai method `echoJson` và `echoForm` có cùng URL + method nhưng khác `consumes`; chọn bằng `Content-Type`.
- `manual` minh họa `@RequestMapping(method=RequestMethod.PUT)` tương đương về HTTP method với `@PutMapping`.
- `search` chỉ là mapping ứng viên khi query param `q` có mặt.
- `partner` chỉ match khi header `X-Client=demo` hiện diện.
- Những kiểm tra body trong controller diễn ra **sau khi mapping thành công**.

Code demo không sử dụng database và không lưu object đã POST. Một POST có body trả kết quả ngay không nhất thiết phải trả 201 Created; ví dụ `echo` trả mặc định **200 OK**, đúng với ý nghĩa echo mà không tạo resource.

## 9. Chạy và gửi HTTP requests

Với JDK 21 và một bản Gradle tương thích (ví dụ 8.5), nếu chưa có wrapper:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Nếu project đã có Gradle wrapper, chỉ chạy `./gradlew bootRun`. Trên Windows PowerShell dùng `.\gradlew.bat bootRun`. Ứng dụng mặc định thường khởi động Tomcat trên port 8080 trừ khi có cấu hình khác.

### 9.1. GET JSON theo path

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/catalog/items/1
~~~

Kỳ vọng HTTP **200** và JSON có dữ liệu:

~~~json
{"id":1,"name":"Notebook"}
~~~

Với `/api/catalog/items/2`, controller quyết định trả **404 Not Found**, không phải vì path mapping thất bại mà vì logic không tìm thấy tài nguyên.

### 9.2. Cùng path GET nhưng hai representations

JSON:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/catalog/representation
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"hello"}
~~~

Text:

~~~bash
curl -i \
  -H "Accept: text/plain" \
  http://localhost:8080/api/catalog/representation
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

hello
~~~

Đây là **phác thảo các dòng có ý nghĩa**, không phải bản sao đầy đủ của header thực tế: Tomcat và Spring có thể thêm header, charset hay thay đổi thứ tự. Chú ý phải gửi `Accept` rõ ràng, vì trong demo có hai endpoint khác nhau cùng path/method.

### 9.3. Cùng POST /echo nhưng hai request content types

Gửi JSON:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/catalog/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Lan"}'
~~~

Kỳ vọng HTTP **200** và:

~~~json
{"source":"json","name":"Lan"}
~~~

Gửi form:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/catalog/echo \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept: application/json" \
  --data-urlencode "name=Lan"
~~~

Kỳ vọng HTTP **200** và:

~~~json
{"source":"form","name":"Lan"}
~~~

Cả hai cùng path và HTTP method nhưng Spring chọn **hai controller methods khác nhau** nhờ `consumes`. Query parameter `name` không quyết định handler nào ở đây; `Content-Type` mới là điều kiện phân biệt.

### 9.4. PUT text/plain

~~~bash
curl -i -X PUT \
  http://localhost:8080/api/catalog/manual \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "abc"
~~~

Kỳ vọng HTTP **200** với body:

~~~text
received:abc
~~~

Khi gửi `POST` thay vì PUT tới `/manual`, request có khả năng trả **405 Method Not Allowed** nếu không có mapping POST khác cho cùng path.

### 9.5. params và headers

~~~bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8080/api/catalog/search?q=java"

curl -i \
  -H "Accept: application/json" \
  -H "X-Client: demo" \
  "http://localhost:8080/api/catalog/partner"
~~~

Kết quả JSON tương ứng:

~~~json
{"query":"java"}
~~~

~~~json
{"access":"demo"}
~~~

Không nên dùng header `X-Client` trong demo như chứng cứ authentication. Đây chỉ là **điều kiện route**, client hoàn toàn có thể tự gửi header đó; với API nội bộ thật vẫn cần cơ chế xác thực, phân quyền và gateway controls.

## 10. Kiểm thử định tuyến bằng MockMvc

Không chỉ test status 200; nên test cả **method không hợp lệ, consumes không hợp lệ và produces không phù hợp**. Đó là cách xác minh điều kiện mapping thực tế.

**src/test/java/com/example/routing/CatalogControllerTest.java**

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getItemReturnsJson() throws Exception {
        mvc.perform(get("/api/catalog/items/1")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Notebook"));
    }

    @Test
    void getMissingItemReturns404() throws Exception {
        mvc.perform(get("/api/catalog/items/2")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound());
    }

    @Test
    void getSamePathWithDifferentAccept() throws Exception {
        mvc.perform(get("/api/catalog/representation")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"));

        mvc.perform(get("/api/catalog/representation")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isOk())
            .andExpect(content().string("hello"));
    }

    @Test
    void postJsonUsesJsonHandler() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.source").value("json"));
    }

    @Test
    void postFormUsesFormHandler() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .param("name", "Lan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.source").value("form"));
    }

    @Test
    void unsupportedRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("Lan"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void unacceptableResponseTypeReturns406() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_XML)
                .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void wrongHttpMethodReturns405() throws Exception {
        mvc.perform(post("/api/catalog/manual")
                .contentType(MediaType.TEXT_PLAIN)
                .content("abc"))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void putManualReturnsText() throws Exception {
        mvc.perform(put("/api/catalog/manual")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .content("abc"))
            .andExpect(status().isOk())
            .andExpect(content().string("received:abc"));
    }

    @Test
    void requestParamAndHeaderConditionsMatch() throws Exception {
        mvc.perform(get("/api/catalog/search")
                .param("q", "java")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.query").value("java"));

        mvc.perform(get("/api/catalog/partner")
                .header("X-Client", "demo")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access").value("demo"));
    }
}
~~~

Chạy test:

~~~bash
./gradlew test
~~~

Trong `@WebMvcTest`, MockMvc thực thi Spring MVC test slice mà không cần mở network socket thực; nó kiểm tra matching, argument binding và response conversion. Ví dụ controller không cần service bean nên không cần mock dependency bên ngoài. Nếu ứng dụng thêm Spring Security hoặc custom web filters, kết quả test có thể bị ảnh hưởng và cần cấu hình auth/CSRF đúng.

Điểm mạnh của bộ test: khi thay đổi `consumes`/`produces` hoặc thêm mapping mới, các case 415/406/405 sẽ phát hiện hành vi ngoài ý muốn trước khi deploy.

## 11. Bốn lỗi HTTP quan trọng khi debug mapping

| Status | Mô tả ngắn | Câu hỏi đầu tiên |
| --- | --- | --- |
| **404 Not Found** | Không có mapping/tài nguyên phù hợp, hoặc controller cố ý trả 404 | Path, context path, controller scan, resource tồn tại? |
| **405 Method Not Allowed** | Path có khả năng được phục vụ nhưng HTTP method không được hỗ trợ | Gửi GET hay POST/PUT? |
| **415 Unsupported Media Type** | Content-Type/request representation không được chấp nhận | Body đang là JSON, form hay text? |
| **406 Not Acceptable** | Không có response representation phù hợp Accept | Client yêu cầu JSON, XML hay text? |

Các mã trên không phải “một lỗi có đúng một nguyên nhân”:

- 404 cũng có thể do tài nguyên nghiệp vụ không tồn tại.
- 405 có thể xuất hiện ở web layer dù controller chưa chạy.
- 415 có thể liên quan mapping `consumes` hoặc converter không thể đọc request media type.
- 406 có thể liên quan `produces` hoặc không thể chọn writer thích hợp.

### 11.1. Ví dụ chẩn đoán có thứ tự

Giả sử client gọi `POST /api/catalog/echo` và nhận 415.

1. Kiểm tra URL, context path và HTTP method.
2. In request headers thực tế; có `Content-Type` hay không?
3. Nếu đang gửi text/plain nhưng endpoint chỉ nhận JSON/form, sửa request theo contract.
4. Nếu đã gửi JSON, kiểm tra media type có parameter bất thường không.
5. Kiểm tra mapping có nhiều handlers `consumes` khác nhau không.
6. Nếu mapping đúng mà vẫn lỗi, xem message converters và khả năng deserialize.
7. Đọc logs/test để phân biệt lỗi mapping và lỗi argument resolution.

Nếu client nhận 406, đổi trọng tâm sang `Accept` và khả năng tạo representation. Không sửa `Content-Type` theo phản xạ vì nó giải quyết câu hỏi khác.

### 11.2. Tránh đánh đồng CORS với mapping

Trình duyệt có thể phát **OPTIONS preflight** trước POST/PUT cross-origin. Nếu CORS chưa được cấu hình, browser có thể chặn request dù controller `@PostMapping` đúng. Không sửa endpoint thành GET để “né CORS”; cần cấu hình CORS policy ở đúng layer, kiểm tra method/headers cho preflight và giới hạn origin tin cậy.

### 11.3. Reverse proxy và context path

Một request bên ngoài có thể đi qua gateway với prefix `/service-a`, trong khi ứng dụng nhận `/api/catalog`. Nếu gateway rewrite path, controller mapping khớp đường dẫn **sau khi rewrite**, không nhất thiết đúng URL browser đang hiển thị.

Khi 404 ở production nhưng chạy được local, kiểm tra `server.servlet.context-path`, proxy rewrite, forwarded headers, route configuration và logs thực tế.

## 12. Tại sao hai mappings có thể bị ambiguous?

Spring chọn mapping tốt nhất dựa trên điều kiện phù hợp. Xung đột thường gặp:

~~~java
@GetMapping("/api/items")
public Object one() { ... }

@GetMapping("/api/items")
public Object two() { ... }
~~~

Đây là **mã phản diện minh họa**, không phải source code cần dùng. Vì hai methods cùng conditions, framework có thể báo lỗi ambiguous mapping khi tạo application context.

Trường hợp khác:

~~~java
@GetMapping(path = "/api/value", produces = "application/json")
public Object json() { ... }

@GetMapping(path = "/api/value", produces = "text/plain")
public Object text() { ... }
~~~

Chúng không giống hệt nhau vì `produces` khác; nhưng client `Accept: */*` có thể không cung cấp đủ thông tin để quyết định như mong muốn. Cách thiết kế an toàn tùy API:

- Dùng đường dẫn khác nhau khi hai representations có ý nghĩa nghiệp vụ khác nhau.
- Xác định rõ contract Accept và test với những Accept phổ biến.
- Tránh khai báo mappings trùng lặp chỉ để “dự phòng”.
- Nếu ứng dụng cần default representation, thiết kế rõ ưu tiên chứ không giả định Spring chọn method khai báo trước.

Khi startup gặp ambiguous mapping, phải xem toàn bộ **điều kiện mapping**, không chỉ tên Java method; việc đổi tên `one()` thành `oneV2()` thường không giải quyết xung đột.

## 13. Annotation inheritance, composition và các tình huống đặc biệt

### 13.1. Shortcuts là composed annotations

`@GetMapping` được xây trên `@RequestMapping(method = RequestMethod.GET)`. Tương tự các annotation POST/PUT/PATCH/DELETE.

Chọn shortcut khi method rõ ràng. Chỉ dùng `@RequestMapping(method=...)` khi muốn nhiều methods chung một handler hoặc khi xây annotation tổ hợp có kiểm soát.

### 13.2. Không gắn nhiều mapping annotations lên cùng element

Không làm:

~~~java
@GetMapping("/x")
@PostMapping("/x")
public String mixed() { ... }
~~~

Nhiều composed `@RequestMapping` trên cùng method không tạo ra một mapping hợp lệ cho hai methods theo cách kỳ vọng; framework có thể chỉ sử dụng annotation đầu và cảnh báo.

Nếu thật sự cần cùng implementation cho nhiều HTTP methods, khai báo rõ:

~~~java
@RequestMapping(
    path = "/x",
    method = {RequestMethod.GET, RequestMethod.POST}
)
public String mixed() {
    return "ok";
}
~~~

Đây là **đoạn minh họa**, không phải lời khuyên rằng GET và POST luôn nên chia sẻ logic. Kiểm tra lại safety/idempotency semantics và security policy trước khi gộp.

### 13.3. params và headers không phải authentication

`params="apiKey"` chỉ kiểm tra tham số có mặt, không kiểm tra API key hợp lệ. `headers="X-Client=partner"` chỉ kiểm tra chuỗi header, client có thể tự điền. Hãy dùng security filter/configuration, token signature verification và access policy đúng tiêu chuẩn.

### 13.4. consumes/produces không đảm bảo security hoặc data validation

`consumes="application/json"` không tự validate payload và không tự chống tấn công. Cần giới hạn request size, input validation, authentication/authorization, output encoding phù hợp và kiểm soát serialization nhạy cảm.

### 13.5. Multipart và form là những trường hợp cần API tương ứng

`multipart/form-data` thường dùng `MultipartFile`/`@RequestPart` trong Spring MVC và `application/x-www-form-urlencoded` thường dùng `@RequestParam`/form binding. Đừng mặc định dùng `@RequestBody MyDto` cho mọi định dạng vì converter/binding khác nhau.

### 13.6. Media type với version

Một số API dùng vendor media type như `application/vnd.example.v2+json`. Điều này có thể là một phần content negotiation, nhưng đòi hỏi rõ contract và message writer có thể tạo/đọc loại media type tương ứng. Đừng tự gán nhiều media types chỉ để các client luôn được match; versioning cần thiết kế tương thích.

## 14. Best practices khi thiết kế contract routing

1. **Khai báo HTTP method rõ ràng** trên từng endpoint, ưu tiên `@GetMapping`/`@PostMapping`/... .
2. **Sử dụng URL ổn định và có nghĩa**, phân biệt collection và item resources.
3. **Khai báo `consumes` khi endpoint nhận định dạng body cụ thể**, nhất là khi cùng URL có handler cho JSON và form.
4. **Khai báo `produces` khi hợp đồng response cần rõ định dạng**, ví dụ JSON vs text/SSE.
5. **Dùng `MediaType` constants** thay vì các chuỗi media type tự đặt tùy tiện.
6. **Tách mapping và data binding**, không cho rằng `@RequestBody` có thể thay thế `consumes`.
7. **Đừng ngầm dùng `@RequestMapping` không có method** cho API chỉ dành GET.
8. **Đảm bảo không có mappings ambiguous** trong cùng context và đường đi deployment.
9. **Test Accept/Content-Type cả chiều đúng và sai**, bao gồm 405, 415, 406.
10. **Không dùng headers/params mapping để thay authentication và authorization**.
11. **Xem lại class-level `consumes`/`produces`** trước khi method-level khai báo override.
12. **Đồng bộ gateway, context path và CORS**, đừng chỉ xem controller annotations.
13. **Đo thực tế bằng integration tests** khi có custom converters, proxies hoặc API clients đặc biệt.
14. **Tài liệu hóa response error/schema**, vì cùng một status có thể do nhiều tầng xử lý.

## 15. Checklist khi code hoặc review một endpoint

Trước khi chấp nhận một route mới, tự trả lời:

- HTTP method được khai báo rõ chưa? Nó có phù hợp ngữ nghĩa safe/idempotent?
- Class-level path và method-level path ghép lại đúng URI không?
- Cần điều kiện `params` hoặc `headers` để chọn route không? Có nguy cơ cùng conditions với route khác?
- Request body được gửi bằng media type nào? `consumes` có khớp và có converter để đọc không?
- Client dự kiến gửi `Accept` gì? `produces` có khớp và có writer để tạo không?
- Đã phân biệt `Content-Type` của request với `Content-Type` của response chưa?
- `@RequestBody`, `@RequestParam`, `@PathVariable` có binding đúng không?
- DTO có validation cần thiết và error handling rõ ràng chưa?
- Với request không hợp lệ, 400/404/405/406/415 có hành vi nhất quán và test chưa?
- Với `Accept: */*` hoặc Accept vắng mặt, behavior có được định nghĩa rõ và không ambiguous chưa?
- Có reverse proxy rewrite, context path hoặc CORS làm thay đổi thực tế request không?
- Authorization đã dùng security policy thay vì giả định POST/header là đủ chưa?
- Các endpoint JSON/form cùng URL có được test riêng không?
- Có dùng Spring MVC hay WebFlux đúng stack mong muốn? Có cả hai starter trên classpath không?
- Có tài liệu hoặc OpenAPI contract mô tả đầy đủ method, request/response media types không?

**Kết luận:** `@RequestMapping` chọn controller method theo **path + HTTP method + các điều kiện params/headers + media types**. `consumes` kiểm soát những kiểu **request Content-Type** được nhận; `produces` kiểm soát những kiểu **response** có thể cung cấp theo `Accept`. Chúng là điều kiện **định tuyến**, không thay thế body binding, JSON conversion, input validation hay security. Hiểu chính xác ranh giới này giúp thiết kế API rõ contract, tránh ambiguous mappings và giải thích đúng các lỗi 405, 415, 406.

## Tài liệu tham khảo

- [Spring Framework — Spring MVC Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): path, method, params, headers, consumes, produces; class/method-level conditions.
- [Spring Framework — Spring WebFlux Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): annotated routing tương ứng trên reactive stack.
- [Spring Framework 6.1 — @RequestMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): mô tả chi tiết các thuộc tính.
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java, Gradle và Servlet container tương thích.
- [Spring Boot 3.3 — Gradle Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/): plugin, dependency management và cách chạy.
