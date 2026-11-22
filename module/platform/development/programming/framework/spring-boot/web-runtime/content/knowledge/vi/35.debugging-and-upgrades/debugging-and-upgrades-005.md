# 405, 406 và 415 do phương thức hoặc định dạng không khớp trong Spring Boot

## 1. Đọc đúng ý nghĩa ba mã trước khi sửa API

Một client gọi đúng hostname và nghĩ rằng URL `/api/products` đúng, nhưng server trả một trong ba mã lỗi:

- **405 Method Not Allowed:** phương thức HTTP (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`...) không phù hợp với tài nguyên/route.
- **406 Not Acceptable:** server không tạo được một representation của **response** phù hợp các media types client yêu cầu trong `Accept`.
- **415 Unsupported Media Type:** loại representation của **request body** khai trong `Content-Type` không được endpoint/decoder chấp nhận.

Chúng đều là lỗi hợp đồng HTTP nhưng khác tầng. Không “sửa nhanh” bằng cách mở `@RequestMapping` cho mọi method, xóa mọi `consumes`/`produces` hay trả `200 OK` cho mọi lỗi. Hãy sửa **phía client gửi sai yêu cầu**, hoặc thay đổi API contract phía server **khi nghiệp vụ thật sự cần**.

Bài học dùng **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 21, Gradle và JUnit 5**; phần lớn khái niệm đúng với Java 17+. Ví dụ MVC và WebFlux là **hai ứng dụng riêng**. Status thực của một request vẫn có thể bị thay đổi bởi Spring Security, reverse proxy, gateway, CORS, custom exception handler, path matching hay content negotiation configuration. Các response error bodies trong bài chỉ là minh họa, không phải output byte-exact của mọi hệ thống.

## 2. Ba chiều HTTP phải tách riêng

```text
HTTP request
   |
   +-- request method: GET / POST / PUT / PATCH / DELETE
   |        └── @GetMapping, @PostMapping, ... ─── 405
   |
   +-- Content-Type: request body là JSON/XML/text/multipart?
   |        └── consumes + input reader ───────── 415
   |
   +-- Accept: response client chấp nhận JSON/XML/text?
            └── produces + output writer ──────── 406
```

Một request POST hợp lệ:

```http
POST /api/products HTTP/1.1
Host: 127.0.0.1:8080
Content-Type: application/json
Accept: application/json

{"name":"Pen"}
```

Trong đó `Content-Type` mô tả **bytes đang gửi đến server**. `Accept` mô tả **cách biểu diễn dữ liệu client muốn server trả về**. Chúng có thể có giá trị giống nhau nhưng không phải cùng một header.

Nếu controller nhận JSON nhưng trả `text/plain`, request hợp lệ có thể dùng `Content-Type: application/json` đồng thời `Accept: text/plain`. Nếu controller nhận text và trả JSON, hai header sẽ đảo lại. Còn HTTP method là một ràng buộc độc lập, không liên quan trực tiếp tới JSON hay XML.

## 3. Bảng đối chiếu 405/406/415 cùng những mã dễ nhầm

| Status | Tên | Khi nào nghi ngờ? | Kiểm tra |
| --- | --- | --- | --- |
| **405** | Method Not Allowed | Cùng path có mapping nhưng method không phù hợp | Actual method, `@...Mapping`, `Allow` |
| **406** | Not Acceptable | Server không tạo được output client muốn nhận | `Accept`, `produces`, response converter |
| **415** | Unsupported Media Type | Server không đọc được loại body client gửi | `Content-Type`, `consumes`, input converter |
| **400** | Bad Request | JSON malformed, argument binding lỗi, thiếu body bắt buộc | Body syntax, DTO, validation |
| **404** | Not Found | Path không match (hoặc tài nguyên được che) | Path, context path, proxy rewrite |
| **401/403** | Auth/security errors | Security filter chặn trước controller | Credentials, ACL, CSRF, CORS |
| **413** | Content Too Large | Body vượt size limit | Proxy/servlet/codec limits |
| **422** | Unprocessable Content | Một số API dùng cho validation nghiệp vụ | Contract API cụ thể; không mặc định do Spring |
| **500** | Server error | Unexpected conversion/serialization/custom handler bug | Exception stack và codec configuration |

**Không suy status chỉ từ một header đơn lẻ.** Request có thể sai cả method lẫn media type. Spring mapping xem nhiều điều kiện và các filter có thể trả lỗi trước; test chẩn đoán nên giữ các chiều khác **đúng** rồi chỉ thay đúng một chiều cần kiểm tra.

## 4. Request đi qua những tầng nào trong Spring MVC?

```text
Browser/SDK -> proxy/WAF -> Tomcat (Servlet)
                              |
                              v
                    Servlet filters / Security / CORS
                              |
                              v
                        DispatcherServlet
                              |
                              v
                    RequestMappingHandlerMapping
                      path, method, params, headers,
                      consumes, produces
                              |
             +----------------+----------------+
             |                |                |
          mapping          argument         response
          mismatch         reader           writer
           405/...         415/400          406/500
                              |
                              v
                       Controller/service
                              |
                              v
                      HTTP status/headers/body
```

`@RestController` không tự bỏ qua routing. Controller có thể **không được gọi** nếu method, `consumes` hoặc `produces` không khớp. Sau khi mapping thành công, `@RequestBody` còn phải được một `HttpMessageConverter` đọc. Sau khi handler trả dữ liệu, `@ResponseBody`/`ResponseEntity` còn phải được một converter ghi ra media type có thể chấp nhận.

Do đó 415 có thể phát sinh tại **mapping** hoặc lúc **đọc body**; 406 có thể phát sinh tại **mapping** hoặc khi **chọn representation cho output**. Một lỗi converter khi serialize đã chọn handler cũng có thể trở thành 500. Không gán cứng mọi 406/415 cho đúng một dòng code.

## 5. 405: HTTP method không khớp route, không phải lỗi JSON

Giả sử controller chỉ khai:

```java
@GetMapping("/api/products/{id}")
public ProductView get(@PathVariable String id) {
    return new ProductView(id, "Demo item");
}
```

Client gửi:

```http
POST /api/products/p1 HTTP/1.1
Content-Type: application/json

{"name":"Pen"}
```

Ở đây `POST /api/products/p1` **không có mapping** trong ví dụ, nhưng `GET /api/products/p1` có. 405 là lỗi contract thích hợp. Sửa bằng cách gọi **GET** để đọc tài nguyên, hoặc thiết kế endpoint POST/PUT/PATCH riêng nếu nghiệp vụ có action ghi.

Các nguồn thường gây 405:

- `fetch(url)` hoặc `curl` thực tế dùng `GET` trong khi API chỉ có `POST`.
- HTML form mặc định GET, hoặc `method="post"` không thể trực tiếp tạo `PUT`.
- SDK/HTTP client chọn sai verb.
- Redirect chain làm request cuối có method khác dự kiến.
- Gateway/WAF chặn `PATCH`, `DELETE`, `OPTIONS`.
- Route có class-level prefix khác tài liệu.
- Browser preflight `OPTIONS` bị security/proxy chặn.

Không đưa ra lời khuyên “đổi `@GetMapping` thành `@RequestMapping` cho phép mọi method” chỉ để hết 405. GET có semantics safe/idempotent khác POST; mở sai method có thể làm phát sinh security/caching issues.

## 6. Header `Allow` là gợi ý quan trọng với 405

Một response có thể có:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
```

Theo HTTP semantics, response 405 cần thông tin methods hiện được hỗ trợ cho tài nguyên đích qua `Allow`. Spring MVC/WebFlux thường cung cấp thông tin này dựa trên mappings. Nhưng **không phụ thuộc** vào thứ tự/nội dung byte-exact vì framework có thể xử lý `HEAD`, `OPTIONS` tự động và proxy có thể thêm/sửa headers.

Ví dụ client gửi `GET /api/products` khi chỉ có `POST /api/products`: `Allow` có thể nhắc POST. `Allow` là manh mối rằng path được xử lý bởi **một mapping khác method**, không phải bằng chứng controller mà bạn mong đợi đã chạy.

Khi `Allow` kỳ lạ, kiểm tra toàn bộ mappings thực tế, wildcard route, filter/router order và ingress rewrites. Không để frontend suy từ header rằng người dùng có quyền thực thi mọi method được liệt kê; `Allow` khác authorization.

## 7. HEAD và OPTIONS không giống mọi method khác

Spring Framework 6.1 hỗ trợ HTTP `HEAD` cho `@GetMapping` theo behavior thông dụng. Header của `HEAD` có thể tương tự GET nhưng **không có response body**. Vì vậy:

```bash
curl -I http://127.0.0.1:8080/api/products/p1
```

thường không phải testcase 405 chỉ vì controller không khai `@HeadMapping`.

Tương tự, Spring MVC/WebFlux có handling tự động cho HTTP `OPTIONS`, thường trả `Allow` khi route phù hợp. Browser CORS preflight là một **OPTIONS request đặc biệt**, có `Origin` và `Access-Control-Request-Method`, đôi khi bị reverse proxy hoặc Spring Security chặn trước controller.

Nếu browser gửi POST JSON tới origin khác, developer phải xem **OPTIONS có thành công chưa**, rồi mới phân tích POST có trả 405/406/415. Không thêm `@PostMapping` để sửa một preflight OPTIONS policy.

## 8. 405 khác 404 thế nào?

Trong demo có:

```text
GET  /api/products/p1 -> route GET phù hợp, handler có thể trả 200
POST /api/products/p1 -> path có GET nhưng không POST, thường 405
GET  /api/unknown     -> không có path mapping, thường 404
```

Nhưng HTTP status không phải phép thử tuyệt đối cho “URL đúng”: có thể request đang tới **một API gateway** hoặc **một handler wildcard** khác; response 405/404 do nơi đó phát ra. Một hệ thống có auth có thể cố ý trả 404 để không lộ sự tồn tại tài nguyên.

Để phân biệt, ghi route template đã match, service/instance version và correlation ID đã chuẩn hóa; không log URL đầy đủ nếu path/query mang PII, credentials hoặc signed tokens.

## 9. Cẩn thận với `curl -d` và redirect khi điều tra 405

Lệnh:

```bash
curl -d '{"name":"Pen"}' http://127.0.0.1:8080/api/products
```

gửi **POST** theo mặc định, dù không ghi `-X POST`. Vì vậy một người đang kiểm tra GET mà lỡ thêm `-d` có thể nhận 405 do method đổi.

Ngược lại:

```bash
curl -i http://127.0.0.1:8080/api/products
```

là GET. Muốn tái hiện rõ:

```bash
curl -i -X GET http://127.0.0.1:8080/api/products
curl -i -X POST http://127.0.0.1:8080/api/products
```

HTTP redirects cũng cần xem: các clients có thể thay POST thành GET khi follow `301`/`302` ở một số trường hợp, còn `307`/`308` giữ method theo HTTP semantics. Khi debug, dùng verbose trace **đã loại credentials** hoặc xem Network tab; không chỉ nhìn final URL sau redirect.

## 10. 415: server không chấp nhận media type của request body

Controller:

```java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public ProductView create(@RequestBody CreateProductRequest input) {
    return new ProductView("p1", input.name());
}
```

Client gửi:

```http
POST /api/products HTTP/1.1
Content-Type: text/plain
Accept: application/json

{"name":"Pen"}
```

Body nhìn như JSON nhưng header nói `text/plain`. `consumes=application/json` không cho phép mapping nhận loại input đó. Response **415 Unsupported Media Type** là hợp lý.

Sửa bằng cách gửi **Content-Type đúng** cùng JSON hợp lệ. Nếu khách hàng thật sự muốn gửi text/plain, API cần **một representation/handler riêng** có test, không chỉ xóa điều kiện `consumes` cho phép mọi loại body.

## 11. `consumes` và request decoder là hai lớp kiểm tra

`consumes` hạn chế routing:

```java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE)
```

Sau khi chọn method, `@RequestBody` còn cần Spring `HttpMessageConverter` (MVC) hoặc `HttpMessageReader` (WebFlux) tương thích với input type. Những trường hợp:

1. Header `Content-Type: text/plain`, mapping chỉ nhận JSON → **415** tại matching.
2. Mapping không ràng buộc `consumes`, nhưng không có converter đọc body theo type → cũng có thể **415**.
3. Header và converter đúng nhưng body `{"name":` malformed → thường **400**.
4. Body JSON hợp lệ nhưng DTO validation fail → thường 400 với Bean Validation hoặc status theo API contract.
5. Body quá lớn → có thể 413 hoặc response khác do proxy/server/codec limits.
6. Charset/parameters không hợp lệ → cần xác định lỗi ở media matching hay decoding; không mặc định mọi case là 415.

`@RequestBody(required=true)` không thay `consumes`. Một body vắng mặt có thể gây 400 dù `Content-Type` khai đúng JSON. Ngược lại, một media type hợp lệ không bảo đảm JSON parser hoặc business validation thành công.

## 12. `Content-Type` thiếu, charset, vendor JSON

Trong JSON API:

```http
Content-Type: application/json
```

và:

```http
Content-Type: application/json;charset=UTF-8
```

thông thường đều tương thích với mapping `consumes="application/json"` trên Spring Framework 6.1. Spring xử lý media type parameters và compatibility, không dùng so sánh `String.equals("application/json")` đơn giản.

Nếu request có body JSON mà **không có Content-Type**, một API JSON-only có thể từ chối bằng 415. Không dựa vào server tự đoán JSON từ ký tự đầu `{`.

Một vendor type như:

```http
Content-Type: application/vnd.example.product+json
```

có thể được một Jackson converter hỗ trợ qua `application/*+json`, nhưng **điều đó không tự bảo đảm** `@PostMapping(consumes="application/json")` match vendor media type. Nếu API có hợp đồng vendor JSON, phải khai `consumes` cụ thể và kiểm thử mapping **cùng converter**.

Không dùng `consumes="!text/plain"` để vô tình chấp nhận mọi thứ khác text; whitelist media types theo nghiệp vụ thường dễ kiểm soát hơn.

## 13. `curl -d` mặc định không gửi JSON Content-Type

Lỗi phổ biến:

```bash
curl -i \
  -d '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/products
```

Dù body trông JSON, curl thường đặt `Content-Type: application/x-www-form-urlencoded`. Với controller JSON-only, 415 là kết quả có thể dự đoán.

Sửa:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/products
```

Trên curl có hỗ trợ `--json`:

```bash
curl -i --json '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/products
```

`--json` hỗ trợ gửi body và đặt các headers JSON liên quan; kiểm tra `curl --version` của CI runner. Đừng coi `-d`/`--data-raw` và `--json` có cùng default headers.

## 14. Multipart và form data là hai kiểu input khác JSON

| Body client gửi | Content-Type thường dùng | Binding phù hợp |
| --- | --- | --- |
| JSON | `application/json` | `@RequestBody SomeDto` và Jackson |
| Text | `text/plain` | `@RequestBody String` |
| HTML form | `application/x-www-form-urlencoded` | `@RequestParam`, `@ModelAttribute` trong MVC |
| Multipart | `multipart/form-data; boundary=...` | `MultipartFile`, `@RequestPart` MVC; `FilePart` WebFlux |
| XML | `application/xml` | XML codec/converter và model thực sự được hỗ trợ |
| Binary | `application/octet-stream` | Byte array/stream/`DataBuffer` theo stack |

Một endpoint `@PostMapping(consumes="application/json")` sẽ không tự đọc một browser form `application/x-www-form-urlencoded`. Nếu app cần form, thiết kế handler riêng và input binding phù hợp.

Với multipart:

```bash
curl -i -F 'file=@sample.txt' \
  http://127.0.0.1:8080/api/uploads
```

`curl -F` tạo boundary. **Đừng** set thủ công `Content-Type: multipart/form-data` thiếu boundary. Nếu gặp 415/400 trong upload, kiểm tra mapping `consumes`, multipart codec, boundary, max size và `@RequestPart` name. Các lỗi multipart parsing không phải tất cả đều là 415.

## 15. 406: server không thể sinh response hợp `Accept`

Một JSON-only endpoint:

```java
@GetMapping(
    path = "/api/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
public ProductView get(@PathVariable String id) {
    return new ProductView(id, "Demo item");
}
```

Client gửi:

```http
GET /api/products/p1 HTTP/1.1
Accept: application/xml
```

Client chỉ muốn XML trong khi mapping chỉ công bố JSON; Spring có thể trả **406 Not Acceptable**. Đây là **output negotiation**, không phải vấn đề Content-Type của request: GET có thể không có request body.

Nếu sản phẩm thật chỉ hỗ trợ JSON, sửa client thành:

```http
Accept: application/json
```

Không mở XML output chỉ để một cấu hình Postman sai bỗng thành công. Nếu client thật sự cần XML, phải xây representation XML, codec/converter, model và compatibility tests.

## 16. `produces` khác việc cài message converter

Ví dụ:

```java
@GetMapping(
    path = "/api/products/{id}",
    produces = {"application/json", "application/xml"})
```

Chỉ khai rằng mapping **có thể được chọn** khi client chấp nhận một trong hai media types. Nó **không tự thêm Jackson XML** hoặc đảm bảo Java object được serialize thành XML.

Để sinh `application/xml` thật, cần output converter/codec và DTO mapping thích hợp, tùy Spring stack. Nếu không, quá trình write có thể gây `406`, lỗi conversion hoặc một số `500` sau khi handler đã chọn. Do đó **đừng khẳng định mọi lỗi ghi response đều là 406**.

Tương tự, trong MVC `MappingJackson2HttpMessageConverter` xuất JSON khi được hỗ trợ; Spring WebFlux dùng `HttpMessageWriter`. Đừng copy converter configuration MVC vào WebFlux mà mong tất cả writer types giống nhau.

## 17. `Accept` wildcard và q-values

Header `Accept` có thể khai nhiều representations:

```http
Accept: application/json
Accept: application/json, text/plain;q=0.5
Accept: application/*;q=0.9, text/plain;q=0.2
Accept: */*
```

`*/*` trong ví dụ biểu thị wildcard **mọi media type**, sẽ được thay thành cú pháp HTTP thực trong bài đã lưu.

Quality factor `q` thường nằm trong `[0,1]`, với `q=0` biểu thị **không chấp nhận** representation tương ứng. Spring xem compatibility/specificity và khả năng write, không chỉ đọc mục đầu tiên rồi quyết định.

Với endpoint chỉ xuất JSON:

```text
Accept: application/json      -> có thể thành công
Accept: application/*         -> có thể thành công
Accept: */*             -> có thể thành công
Accept: application/xml       -> 406 khi không có XML representation
```

Nếu client dùng `Accept: text/html` từ browser, JSON-only endpoint có thể trả 406; đừng nhầm với browser HTML error page của `/error`, vì **normal response** và **error rendering** có negotiation khác nhau.

`Accept-Encoding: gzip, br` là header cho compression/content coding, không phải media type negotiation JSON/XML. Thay đổi gzip không sửa được 406 do `Accept: application/xml`.

## 18. `consumes`/`produces` trên class và method: chú ý override

Spring Framework cho phép:

```java
@RestController
@RequestMapping(
    path = "/api",
    consumes = "application/json",
    produces = "application/json")
class ExampleController {
    @PostMapping(path = "/plain",
        consumes = "text/plain",
        produces = "text/plain")
    String plain(@RequestBody String value) {
        return value;
    }
}
```

Đây là **mẫu tích hợp**, cần imports/package phù hợp. Đối với `consumes` và `produces`, method-level declarations **override** class-level conditions, không nhất thiết là phép giao của hai danh sách.

Những điểm phải kiểm tra khi đọc code:

- Có annotation `@RequestMapping` ở class/interface không?
- Method `@GetMapping`/`@PostMapping` có ghi đè `consumes`/`produces` không?
- Có `headers="content-type=..."` hoặc `params=...` tạo điều kiện khác không?
- Có hai `@RequestMapping` annotations trên một method? Spring khuyến nghị **không gắn nhiều mapping annotations trên cùng element** vì chỉ một mapping có thể được sử dụng.
- Có `spring.mvc.contentnegotiation.*`/`WebMvcConfigurer` hoặc codec custom thay behavior không?

Dùng `consumes`/`produces` thay vì tự viết điều kiện `headers="Content-Type=..."` để tận dụng media type compatibility/negotiation của framework.

## 19. Code demo MVC: project và phụ thuộc

Ứng dụng này tái hiện riêng 405, 406, 415 trên các routes có contract rõ. Mẫu **không có database và Spring Security**, chỉ bind loopback để tránh dùng sai như public API.

```text
build.gradle
src/main/java/com/example/httpcodes/
    HttpCodesApplication.java
    CreateItemRequest.java
    ItemView.java
    ItemController.java
src/main/resources/application.properties
src/test/java/com/example/httpcodes/
    HttpCodesMvcTest.java
    HttpCodesLiveTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
```

Gradle Wrapper phải được tạo với Gradle version hỗ trợ Java 21; Spring Initializr có thể tạo sẵn. `spring-boot-starter-web` cung cấp MVC, embedded Tomcat và Jackson JSON trong config thông dụng; starter-test hỗ trợ MockMvc/JUnit Jupiter/AssertJ.

## 20. Main class và request/response DTO

**`HttpCodesApplication.java`:**

```java
package com.example.httpcodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCodesApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCodesApplication.class, args);
    }
}
```

**`CreateItemRequest.java`:**

```java
package com.example.httpcodes;

public record CreateItemRequest(String name) {
}
```

**`ItemView.java`:**

```java
package com.example.httpcodes;

public record ItemView(String id, String name) {
}
```

Java records có default accessor `name()`/`id()` và Jackson trong Spring Boot 3.3 có thể bind/serialize chúng. **Record không tự xác thực dữ liệu nghiệp vụ**: `String name` có thể vẫn null nếu client bỏ field và chưa bật Bean Validation. Bài này tập trung HTTP contract; validation thật nên thêm `@Valid`, constraints và tests riêng.

## 21. Controller: một GET JSON, một POST JSON và một POST text

**`ItemController.java`:**

```java
package com.example.httpcodes;

import java.util.Locale;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    @GetMapping(
        path = "/api/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemView get(@PathVariable("id") String id) {
        return new ItemView(id, "Demo item");
    }

    @PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> create(
            @RequestBody CreateItemRequest input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new ItemView("i1", input.name()));
    }

    @PostMapping(
        path = "/api/text/upper",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String upper(@RequestBody String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
```

Ý nghĩa:

- `GET /api/items/i1` có JSON output; `Accept: application/xml` cho lỗi 406.
- `GET /api/items` không có GET mapping, trong khi `POST /api/items` có; dùng để tái hiện 405.
- `POST /api/items` chỉ nhận JSON; `Content-Type: text/plain` cho 415.
- `POST /api/text/upper` minh họa text input/output hợp lệ, tránh lầm rằng mọi endpoint phải nhận JSON.

`create()` trả ID cố định và không lưu vào DB. `GET /api/items/i1` trả tên demo cố định ngay cả sau khi POST tạo item tên khác; **đây là stateless test app**, không phải ví dụ persistence.

## 22. Cấu hình local và chạy HTTP server

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
```

Chạy:

```bash
./gradlew bootRun
```

Không có Security starter trong demo nên requests không bị yêu cầu credentials; đừng triển khai nguyên app không auth lên Internet. Để test case 405/406/415, các curl bên dưới dùng **đúng một chiều sai** tại mỗi lần thử.

## 23. Baseline 200/201 trước khi tái hiện lỗi

GET đúng:

```bash
curl -i \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items/i1
```

Kỳ vọng HTTP `200` và body JSON logic:

```json
{"id":"i1","name":"Demo item"}
```

POST đúng:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/items
```

Kỳ vọng HTTP `201 Created`, JSON body:

```json
{"id":"i1","name":"Pen"}
```

Headers và whitespace có thể khác theo runtime; **đừng assert toàn bộ HTTP response raw**. Kiểm tra status, content type tương thích, JSON field values.

## 24. Tái hiện 405 bằng cách đổi method, giữ path

```bash
curl -i \
  -X GET \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items
```

`/api/items` chỉ có POST mapping → mong đợi `405 Method Not Allowed`. Header `Allow` nên phản ánh supported methods; không assert đúng thứ tự hoặc chính xác toàn bộ chuỗi.

Cách đối chiếu:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/items
```

Chỉ khác method (và sự tồn tại body cần thiết) → thành công. Với method sai, handler tạo item sẽ không được gọi; không cố “fix 405” bằng cách nới Spring Security cho tất cả methods.

## 25. Tái hiện 415 bằng cách đổi request `Content-Type`

```bash
curl -i \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/items
```

Kỳ vọng `415 Unsupported Media Type`. Body vẫn có dấu ngoặc JSON nhưng server **tin contract Content-Type của request**, không nên âm thầm coi mọi text là JSON.

Đối chiếu chỉ sửa:

```http
Content-Type: application/json
```

thì cùng body được đọc thành `CreateItemRequest`. Test này tách input media negotiation khỏi output.

Nếu gửi `Content-Type: application/json` tới `/api/text/upper`, endpoint text-only cũng có thể 415. Điều kiện `consumes` là của **từng handler**, không phải chỉ một property chung của Spring Boot.

## 26. Tái hiện 406 bằng cách đổi response `Accept`

```bash
curl -i \
  -H 'Accept: application/xml' \
  http://127.0.0.1:8080/api/items/i1
```

Kỳ vọng `406 Not Acceptable`, vì endpoint chỉ khai `produces=application/json`. **Không có request body**, vì thế `Content-Type` không phải vấn đề ở request này.

Đối chiếu:

```bash
curl -i \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items/i1
```

sẽ trả JSON.

Với POST, có thể đồng thời gửi **input đúng** `Content-Type: application/json` nhưng **output sai** `Accept: application/xml`; kết quả dự kiến 406. Tuy nhiên trong thí nghiệm tốt, hãy dùng GET để cô lập 406 dễ nhất.

## 27. JSON sai cú pháp trả 400, không mặc định là 415

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":' \
  http://127.0.0.1:8080/api/items
```

Mapping chấp nhận JSON, nhưng parser không đọc được JSON malformed. Spring MVC thường phát `HttpMessageNotReadableException`, response là `400 Bad Request`.

Một body valid JSON nhưng sai constraints (`name` rỗng/thiếu) là **validation issue** khác nữa; phải thêm Bean Validation hoặc business checks rõ ràng. `@RequestBody` cũng có behavior khi body thiếu (`required=true`), thường 400. Không dùng 415 cho mọi input error.

Nếu client khai `application/xml` nhưng body JSON, lỗi 415 xảy ra **trước** khi Jackson JSON có cơ hội parse. Khi test, giữ các yếu tố khác đúng để không đo nhầm.

## 28. `MockMvc`: test các mã độc lập không cần TCP

**`src/test/java/com/example/httpcodes/HttpCodesMvcTest.java`:**

```java
package com.example.httpcodes;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ItemController.class)
class HttpCodesMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonGetWorks() throws Exception {
        mvc.perform(get("/api/items/i1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("i1"))
                .andExpect(jsonPath("$.name").value("Demo item"));
    }

    @Test
    void wrongMethodIs405() throws Exception {
        mvc.perform(get("/api/items")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string(
                        HttpHeaders.ALLOW, containsString("POST")));
    }

    @Test
    void wrongRequestContentTypeIs415() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Pen\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void wrongResponseAcceptIs406() throws Exception {
        mvc.perform(get("/api/items/i1")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void validPostReturns201Json() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Pen\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void correctPlainTextWorks() throws Exception {
        mvc.perform(post("/api/text/upper")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("HELLO"));
    }
}
```

Chạy:

```bash
./gradlew test
```

**Kỳ vọng:** bảy tests đạt PASS khi dependencies, JDK và sources đúng. `MockMvc` dùng Spring MVC handler dispatch/message converters, nhưng **không mở TCP socket** nên không chứng minh gateway/Tomcat TLS/CORS browser hoạt động.

Kiểm tra `Allow` bằng `containsString("POST")` thay vì so toàn bộ header, vì framework có thể thêm handling OPTIONS/ordering. Không assert exact text của 405/406/415 error body vì Spring Boot error formatting có thể khác giữa profiles.

## 29. Real HTTP integration test với `RANDOM_PORT`

**`src/test/java/com/example/httpcodes/HttpCodesLiveTest.java`:**

```java
package com.example.httpcodes;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class HttpCodesLiveTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void callsCorrectEmbeddedServer() {
        assertThat(port).isBetween(1, 65535);

        ResponseEntity<String> result =
                client.getForEntity("/api/items/i1", String.class);
        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody()).contains("\"id\":\"i1\"");
    }

    @Test
    void methodMismatchRemains405OverHttp() {
        ResponseEntity<String> result =
                client.getForEntity("/api/items", String.class);
        assertThat(result.getStatusCode())
                .isEqualTo(HttpStatus.METHOD_NOT_ALLOWED);
    }
}
```

`@LocalServerPort` đọc cổng **OS đã cấp**, còn `TestRestTemplate` trong Boot real-server test có thể dùng relative URL. Không hardcode `localhost:8080` khi chạy `RANDOM_PORT`: test có thể vô tình gọi một process khác.

Các tests live-network hữu ích để phát hiện khác biệt network/Servlet filtering. Muốn kiểm chứng ingress/gateway thực, cần end-to-end setup qua proxy, không chỉ embedded server localhost.

## 30. Spring MVC exception classes để định vị tầng lỗi

| Exception Spring MVC thường gặp | Status liên hệ | Phạm vi |
| --- | --- | --- |
| `HttpRequestMethodNotSupportedException` | 405 | HTTP method mismatch |
| `HttpMediaTypeNotSupportedException` | 415 | Input Content-Type không được hỗ trợ |
| `HttpMediaTypeNotAcceptableException` | 406 | Output Accept/representation không tương thích |
| `HttpMessageNotReadableException` | 400 | JSON/body parse hoặc read error |
| `MethodArgumentNotValidException` | 400 theo default validation | `@Valid` DTO bị từ chối |
| `MissingServletRequestParameterException` | 400 | Required parameter thiếu |
| `HttpMessageNotWritableException` | Có thể 500 | Output codec không ghi được object |
| `NoHandlerFoundException`/`NoResourceFoundException` | 404 theo flow | Không tìm thấy handler/resource |

Không phải một status chỉ có **một** exception nguồn gốc. `@RestControllerAdvice`, `ResponseEntityExceptionHandler`, `DefaultHandlerExceptionResolver`, Security và `/error` có thể tham gia tạo response. Nếu custom handler bắt mọi `Exception` rồi trả 500, bạn có thể **phá cả 405/406/415**.

Để điều tra, xác định exception type và mapping condition mà **không log raw request body hoặc Authorization**.

## 31. ProblemDetail: chuẩn hóa error body nhưng giữ HTTP semantics

Spring Framework 6 hỗ trợ RFC 9457 `ProblemDetail`. Trên Spring Boot 3.3 có thể bật cho MVC:

```properties
spring.mvc.problemdetails.enabled=true
```

Với WebFlux project, Boot có cấu hình tương ứng:

```properties
spring.webflux.problemdetails.enabled=true
```

Response của một 415 có thể có dạng:

```json
{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "The request media type is not supported"
}
```

**Không coi JSON trên là output cố định**: title/detail/instance và media type error thực phụ thuộc exception resolver, localization, Boot config và `Accept` của client. Bật ProblemDetail là **thay error representation**, không làm request sai method hoặc media type thành hợp lệ.

Nếu dùng custom `@ControllerAdvice`:

- Giữ đúng status HTTP và `Allow` header khi 405.
- Giữ đúng content negotiation và các headers liên quan.
- Không catch tất cả framework exceptions thành 500.
- Không expose stack trace, query secrets, credentials trong `detail`.
- Kiểm thử frontend/client có parse `application/problem+json` hay chỉ `application/json`.

## 32. WebFlux khác MVC ở lớp đọc/ghi, không khác ý nghĩa HTTP 405/406/415

Spring WebFlux dùng reactive `DispatcherHandler`, `HttpMessageReader` và `HttpMessageWriter`, thay vì MVC `DispatcherServlet` và `HttpMessageConverter`. Nhưng cùng hợp đồng:

| Vấn đề | MVC | WebFlux |
| --- | --- | --- |
| Method mismatch | `@GetMapping` / `@PostMapping` | Tương tự |
| `Content-Type`/input | `consumes` + converter | `consumes` + reader |
| `Accept`/output | `produces` + converter | `produces` + writer |
| Thường gặp 405 | `HttpRequestMethodNotSupportedException` | `MethodNotAllowedException` |
| Thường gặp 415 | `HttpMediaTypeNotSupportedException` | `UnsupportedMediaTypeStatusException` |
| Thường gặp 406 | `HttpMediaTypeNotAcceptableException` | `NotAcceptableStatusException` |
| Slice test | `@WebMvcTest`/MockMvc | `@WebFluxTest`/WebTestClient |

Exception classes là chi tiết framework, **không phải public wire contract**. Client chỉ nên phụ thuộc vào HTTP status, stable error code và documented response media type.

Nếu server có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường ưu tiên MVC Servlet app type. Một controller trả `Mono` không chứng minh runtime đang WebFlux; cần kiểm tra actual application context và dependencies.

## 33. WebFlux project riêng: Gradle và files

Tạo một project riêng, không trộn với demo MVC:

```text
build.gradle
src/main/java/com/example/fluxerrors/
  FluxErrorsApplication.java
  BookIn.java
  BookOut.java
  BookController.java
src/test/java/com/example/fluxerrors/
  BookWebFluxTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') { useJUnitPlatform() }
```

Không thêm `spring-boot-starter-web` vào runtime khi muốn kiểm thử reactive web server của WebFlux.

## 34. WebFlux controller: cùng hợp đồng, reactive return types

**`FluxErrorsApplication.java`:**

```java
package com.example.fluxerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxErrorsApplication.class, args);
    }
}
```

**`BookIn.java`:**

```java
package com.example.fluxerrors;

public record BookIn(String title) {
}
```

**`BookOut.java`:**

```java
package com.example.fluxerrors;

public record BookOut(String id, String title) {
}
```

**`BookController.java`:**

```java
package com.example.fluxerrors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class BookController {

    @GetMapping(path = "/api/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<BookOut> get(@PathVariable("id") String id) {
        return Mono.just(new BookOut(id, "Demo book"));
    }

    @PostMapping(path = "/api/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookOut>> create(
            @RequestBody Mono<BookIn> input) {
        return input.map(book -> ResponseEntity.status(
                HttpStatus.CREATED)
                .body(new BookOut("b1", book.title())));
    }
}
```

`Mono` là reactive result; nó không tự sửa method/media type mismatch. `@RequestBody Mono<BookIn>` được đọc bằng WebFlux codecs khi request phù hợp.

## 35. WebFlux tests dùng `@WebFluxTest` + `WebTestClient`

**`BookWebFluxTest.java`:**

```java
package com.example.fluxerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(BookController.class)
class BookWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void methodMismatchIs405() {
        client.get()
                .uri("/api/books")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.METHOD_NOT_ALLOWED);
    }

    @Test
    void acceptMismatchIs406() {
        client.get()
                .uri("/api/books/b1")
                .accept(MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.NOT_ACCEPTABLE);
    }

    @Test
    void contentTypeMismatchIs415() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"Spring\"}")
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
    }

    @Test
    void correctJsonCreatesBook() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"Spring\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Spring");
    }
}
```

`@WebFluxTest` tạo mock web layer, không nhất thiết mở Netty socket. Muốn kiểm tra HTTP runtime thật hãy dùng `@SpringBootTest(RANDOM_PORT)` và auto-bound WebTestClient hoặc JDK HttpClient. Đừng kiểm tra WebFlux bằng một `@WebMvcTest` rồi kết luận reactive stack hoạt động.

## 36. Client Spring WebClient/RestClient cũng cần đúng media contract

Một `WebClient` call dễ gây 415:

```java
webClient.post()
        .uri("/api/books")
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue("{\"title\":\"Spring\"}")
        .retrieve()
        .bodyToMono(String.class);
```

**Mẫu tích hợp**, cần WebClient bean/baseUrl và imports. Body trông như JSON nhưng header nói text/plain. Đúng hơn:

```java
webClient.post()
        .uri("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new BookIn("Spring"))
        .retrieve()
        .bodyToMono(BookOut.class);
```

WebClient `retrieve()` mặc định tạo error signal cho nhiều HTTP 4xx/5xx responses. Nếu client code chỉ log `onError`, hãy inspect **actual response status and sanitized headers**, không ném mất thông tin lỗi hoặc retry cùng payload sai vô hạn.

`RestClient`, `RestTemplate`, OkHttp và JDK `HttpClient` cũng phải gửi đúng method/headers; chúng không tự hiểu chuỗi `"{...}"` chắc chắn là JSON.

## 37. Browser `fetch`, HTML form và CORS

Frontend sai method:

```javascript
fetch("/api/items");
```

Mặc định là GET; nếu endpoint chỉ nhận POST, có thể trả 405.

Body đã stringify nhưng header không rõ:

```javascript
fetch("/api/items", {
  method: "POST",
  body: JSON.stringify({name: "Pen"})
});
```

Đừng dựa vào header media type do browser tự suy. Viết rõ:

```javascript
fetch("/api/items", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({name: "Pen"})
});
```

Với cross-origin JSON requests, browser có thể gửi `OPTIONS` preflight trước POST. Nếu preflight bị 403/405 tại security/proxy, request POST **có thể chưa hề được gửi**. Network tab cần hiển thị từng request. CORS là vấn đề origin permission, không phải phép sửa `consumes`/`produces`.

HTML `<form method="post">` thường gửi form-urlencoded khi không có multipart enctype; JSON-only `@RequestBody` không tự nhận mọi HTML form.

## 38. Cấu hình XML, vendor JSON và converter classpath

Khi một API thực sự cần:

```http
Accept: application/xml
```

server phải có JSON/XML representations phù hợp, ví dụ XML converter, mapper, DTO annotations và tests. Chỉ thêm:

```java
@GetMapping(path = "/api/items/{id}",
        produces = {"application/json", "application/xml"})
```

không tự cài converter XML. Hãy kiểm tra dependency tree, Boot BOM và actual response `Content-Type`, body.

Với vendor JSON:

```http
Content-Type: application/vnd.example.product+json
Accept: application/vnd.example.product+json
```

một Jackson converter có thể đọc một số `application/*+json` types, nhưng **mapping** `consumes="application/json"` không tự match mọi vendor type. Nếu API thật sự hỗ trợ vendor JSON, khai đúng input/output media types và kiểm thử từng converter. Không mở mọi suffix `+json` mà không xem contract/version.

Trong `application/problem+json`, chữ `problem+json` là một **error media type**; không đồng nghĩa client `Accept: application/problem+json` yêu cầu business response `application/json` thông thường.

## 39. Security và CORS có thể che mất 405/415 dự kiến

Khi có Spring Security:

- Unauthenticated request có thể nhận `401`.
- Authenticated nhưng không đủ permission có thể nhận `403`.
- Cookie/session POST thiếu CSRF token có thể nhận `403`.
- OPTIONS preflight bị chặn có thể khiến browser báo CORS error, dù POST method/body contract đúng.

Security filters chạy trước handler mapping. Nếu `MockMvc` test 405 bất ngờ nhận 403 sau khi thêm Spring Security, **không** khắc phục bằng cách tắt CSRF trên production. Thêm Spring Security test dependencies, test user/CSRF theo policy, rồi cô lập behavior mapping. Với REST API bearer-token stateless, CSRF strategy cần thiết kế theo authentication mechanism, không áp dụng một recipe cho mọi app.

Một API có `Allow: POST` không có nghĩa caller tự động được authorize cho POST.

## 40. Gateway, redirect và reverse proxy: xác định tầng trả lỗi

Đường đi thực tế:

```text
Client -> CDN/WAF -> API Gateway -> Ingress -> Spring Boot
```

Một 405 có thể do gateway chỉ cho GET/POST và chặn PATCH; một 415 có thể do gateway từ chối request `application/octet-stream` trước khi Spring nhận; một 406 có thể phát sinh từ proxy content negotiation/config caching.

Checklist:

1. Xác định service/instance nào trả status, có trace ID hay response flag phân biệt không.
2. Kiểm tra method/URI thực tế sau redirect hoặc path rewrite.
3. So proxy `Content-Type` và `Accept` forwarded đến app theo policy.
4. Đối chiếu handler mapping đã được đăng ký trong đúng build/version.
5. Kiểm tra default error body/headers là của gateway hay Boot.
6. Không tắt WAF chỉ để làm 415 biến mất; xem data contract và security policy.

Một test localhost PASS không chứng minh API qua ingress PASS. Muốn kết luận root cause, test **cùng request** đi direct-to-app (nếu được phép) và qua proxy trong môi trường kiểm soát.

## 41. Quan sát HTTP an toàn khi tìm lỗi hợp đồng

Một structured log hữu ích:

```json
{
  "event": "http_contract_mismatch",
  "method": "POST",
  "route": "/api/items",
  "status": 415,
  "requestMediaFamily": "text",
  "acceptMediaFamily": "json",
  "serviceVersion": "3.3-demo"
}
```

Đây là **định dạng gợi ý**, không phải Spring Boot tự in theo mặc định. Các trường `Content-Type`/`Accept` từ client có thể chứa chuỗi quá dài hoặc khác thường; normalize thành **category hữu hạn** trước khi đưa vào metrics tags.

Không log:
- Bearer `Authorization`, `Cookie`, `Set-Cookie` hoặc API keys.
- Raw request/response body có PII.
- Full path/query chứa email, code, signed URL.
- Raw user-controlled headers hoặc stack traces không được rà soát.

Ghi method, route template, status, timing, correlation ID và normalized content/accept categories là đủ cho phần lớn chẩn đoán 405/406/415.

## 42. Triệu chứng và hướng tìm nguyên nhân

| Triệu chứng | Nghi ngờ | Hành động kiểm chứng |
| --- | --- | --- |
| POST endpoint nhưng thấy 405 | Client gửi GET hoặc proxy chặn POST | `curl -i -X POST`, `Allow`, gateway logs |
| `curl -d` JSON-looking trả 415 | Default `Content-Type` là form-urlencoded | Gửi header `application/json` |
| `@RequestBody` JSON nhưng XML trả 415 | `consumes`/reader không nhận XML | Contract input + converter |
| Browser yêu cầu XML nhưng JSON API trả 406 | `Accept` chỉ XML | Đổi Accept hoặc bổ sung output XML thật |
| JSON malformed trả 400 | Jackson read/parse failure | Fix body; giữ Content-Type |
| 405 chỉ trên browser | CORS OPTIONS hoặc redirect | Network tab từng request |
| 403 ở MockMvc khi kỳ vọng 415 | Spring Security/CSRF trước mapping | Test auth/csrf |
| HTTP 415 sau nâng cấp | Client headers/converter/classpath thay đổi | Dependency diff, request capture đã sanitize |
| 406 khi thêm `produces=application/xml` | Chưa có XML writer | Test converter/output |
| 500 ở response serialization | Encoder/DTO lỗi | Stack/codec; đừng tự gọi là 406 |
| `@PostMapping` ở method không hoạt động | Component scan, prefix, condition/overlapping mappings | Inspect registered mappings |
| Local PASS, gateway FAIL | Gateway rewrite/media policy | Direct vs proxied smoke test |

## 43. Debug sau nâng Spring Boot hoặc Spring Framework

Khi nâng từ Boot 2.x lên 3.x, cần kiểm tra:

- Spring Framework 6.x, Java 17+ và Jakarta Servlet namespace trong MVC.
- `RequestMappingHandlerMapping` conditions, path pattern/trailing slash differences.
- Body readers/writers và Jackson/codec dependencies đang được Boot BOM quản lý.
- Custom `WebMvcConfigurer` content negotiation, `@ControllerAdvice` và `ResponseEntityExceptionHandler`.
- Spring Security filter chain, CSRF/CORS trước mapping.
- Client `RestTemplate`/`RestClient`/`WebClient`/frontend SDK có đổi default headers không.
- Gateway routing/redirect behavior, Content-Type header forwarding, proxy cache.
- ProblemDetail enabled làm error body từ JSON legacy đổi sang `application/problem+json`.
- Test suites dùng real HTTP ngoài MockMvc/WebFlux slice.

Đừng suy “upgrade đã làm 405 trở thành 415” khi chưa so một **request cố định** (method/path/Content-Type/Accept/body) giữa versions. Giữ regression tests cho 200/201, 400, 404, 405, 406, 415 và security cases theo contract. Mục tiêu là biết **điều kiện nào đổi**, không phán đoán từ status.

## 44. Quy trình chẩn đoán thực tế từng bước

1. **Ghi status** và thời điểm/traceId, không đoán qua text error body.
2. **Xác nhận nơi trả lỗi:** gateway, security, Servlet/WebFlux router hay controller.
3. **Cô lập method:** giữ path và media types đúng, thử method theo API documentation. Với 405 đọc `Allow` nếu có.
4. **Cô lập input media:** giữ method, `Accept`, body syntax đúng; chỉ đổi `Content-Type`; đối chiếu `consumes` và reader.
5. **Cô lập output media:** giữ method/input đúng; chỉ đổi `Accept`; đối chiếu `produces` và writer.
6. **Cô lập syntax:** giữ cả hai media headers đúng rồi gửi JSON malformed; xác nhận 400 khác 415.
7. **Xem mapping hierarchy:** class-level + method-level conditions, wildcard routes, interface annotations, handler order.
8. **Thử local test:** `@WebMvcTest`/`@WebFluxTest`; nếu PASS nhưng full HTTP FAIL, nghi filters/server/proxy.
9. **Thử real HTTP:** `@SpringBootTest(RANDOM_PORT)` và một client không hardcode 8080.
10. **Sửa đúng tầng** và thêm regression test; không mở input/output/method toàn cục.
11. **Kiểm tra trước/sau deployment** trên proxy thật và lưu evidence đã sanitized.

Nếu nhiều điều kiện sai cùng lúc, chia thành các test độc lập. Dòng `Content-Type: application/json` không chứng minh body hợp lệ; `Accept: application/json` không chứng minh server có converter viết Java return type; `@PostMapping` không chứng minh client đã gửi POST.

## 45. Câu hỏi ôn tập

1. Tại sao 405 khác 404 dù cùng một URL?
2. `Allow` trong response 405 dùng để làm gì?
3. Vì sao `HEAD` trên `@GetMapping` thường được xử lý dù không có `@HeadMapping`?
4. Một CORS preflight OPTIONS khác gì POST nghiệp vụ?
5. Body `{"name":"Pen"}` với header `text/plain` gây 415 vì sao?
6. `curl -d` mặc định gửi Content-Type gì?
7. Header nào mô tả request body, header nào mô tả response format mong muốn?
8. Endpoint JSON-only nhận `Accept: application/xml` có thể trả gì?
9. Có Jackson XML dependency nhưng `produces` chỉ JSON, client XML có được bảo đảm thành công không?
10. JSON sai cú pháp nhưng `Content-Type: application/json` thường cho status gì?
11. Method-level `consumes`/`produces` tương tác với class-level thế nào?
12. Vì sao không test đồng thời method sai và Content-Type sai khi xác minh 405?
13. Vendor `+json` cần kiểm tra mapping và converter riêng ra sao?
14. `HttpMessageConverter` khác WebFlux `HttpMessageReader`/`Writer` như thế nào?
15. Vì sao `fetch(url)` có thể gây 405 mà developer nghĩ đang POST?
16. Với Spring Security, 403 có thể xuất hiện trước 415 không?
17. Vì sao không ghi Authorization/cookie/raw body vào production log chỉ để debug 415?
18. Một custom `@ControllerAdvice` bắt mọi Exception rồi trả 500 gây hệ quả gì?
19. Khi gặp 406, vì sao không nên chỉ sửa `Accept-Encoding`?
20. Làm sao biết 415 đến từ gateway hay Spring Boot?
21. Vấn đề nào có thể xảy ra khi nâng Boot 2.x lên 3.x dù method/URL không đổi?
22. Test nào xác nhận thực sự có HTTP socket ngoài mock dispatcher?
23. Tại sao không assert nguyên văn ProblemDetail error body ở mọi release?
24. Khi nào cần thêm media type mới cho API, và khi nào chỉ nên sửa client?
25. Một ứng dụng MVC có thêm WebFlux libraries chỉ để dùng WebClient có chắc là reactive web server không?

**Bài tập A:** Chạy MVC demo. Với cùng route, gửi request đúng trước; sau đó thay một lần method, một lần `Content-Type`, một lần `Accept`. Ghi status và `Allow` nếu có.

**Bài tập B:** Chạy `HttpCodesMvcTest`, thêm test JSON sai cú pháp dẫn đến 400; so sánh với 415 về thời điểm thất bại.

**Bài tập C:** Bật `spring.mvc.problemdetails.enabled=true` ở test profile, đối chiếu status/Allow trước–sau và kiểm tra client parse error media type đúng.

**Bài tập D:** Dùng WebFlux demo, so 405/406/415 với MVC trong `@WebFluxTest`; không dựa vào tên Java exception class làm API.

**Bài tập E:** Đưa một reverse proxy trước Spring Boot; test cùng request qua proxy và direct connection để phân biệt nơi trả error code.

**Bài tập F:** Thêm một route multipart hoặc vendor JSON có chủ đích, viết `consumes` rõ ràng và test đủ cả success/415/400.

## 46. Kết luận và nguồn tham khảo

Ghi nhớ bộ ba:

```text
405 Method Not Allowed
    -> Kiểm tra HTTP method, path/mapping, Allow

415 Unsupported Media Type
    -> Kiểm tra request Content-Type, consumes, input decoder

406 Not Acceptable
    -> Kiểm tra response Accept, produces, output writer
```

Trong Spring Boot, hãy đọc **request thực sự được gửi**, hiểu `@RequestMapping` conditions, phân biệt mapping với conversion, rồi chứng minh bằng `MockMvc`/`WebTestClient` và một real HTTP test. Khi nâng cấp, phải kiểm tra message converter/codec, security, gateway và error response format chứ không chữa bằng cách cho phép mọi media type.

**Tài liệu chính thức để đối chiếu:**

- HTTP Semantics RFC 9110 — HTTP status 405/406/415, Accept, Content-Type, Allow: https://www.rfc-editor.org/rfc/rfc9110.html
- Spring Framework 6.1 — `RequestMapping` API (consumes/produces): https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html
- Spring Framework — MVC mapping requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — WebFlux mapping requests: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — MVC Message Converters: https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html
- Spring Framework — MVC Error Responses/ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Boot 3.3 — Servlet web and error handling: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive web: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Security — CORS integration: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html