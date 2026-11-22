# Phân biệt HTTP 404, 405, 406 và 415 từ điều kiện định tuyến hoặc định dạng trong Spring Boot

Trong ứng dụng Spring Boot, một request không vào được controller có thể trả về **404 Not Found**, **405 Method Not Allowed**, **406 Not Acceptable** hoặc **415 Unsupported Media Type**. Cả bốn đều thuộc nhóm 4xx, nhưng chúng chỉ ra những vấn đề khác nhau: **đường dẫn/tài nguyên**, **HTTP method**, **định dạng response mà client chấp nhận**, và **định dạng request body mà server hỗ trợ**.

Đây không chỉ là khác biệt về thông báo lỗi. Mỗi mã gợi ý một hướng kiểm tra khác nhau, và sửa sai tầng có thể che giấu vấn đề thật. Ví dụ, khi POST JSON nhận 415, đổi URL tùy tiện thường không giúp gì; cần xem **Content-Type** và điều kiện **consumes**. Khi GET nhận 406, thay Content-Type của request chưa chắc đúng vì điều kiện liên quan đến **Accept** của response.

Bài hướng dẫn dựa trên Spring Boot 3.5.x / Spring Framework 6.2.x và Java 17+. Tập trung vào Spring MVC annotated controllers, sau đó phân biệt cách xử lý khi dùng Spring WebFlux, đặc biệt WebFlux.fn RouterFunction. Có ví dụ Spring MVC chạy được, bảng request/status, kiểm thử MockMvc và quy trình gỡ lỗi thực tế.

## 1. Bảng phân biệt nhanh

| Status | Tên HTTP | Câu hỏi nên đặt ra | Tình huống thường gặp |
|---|---|---|---|
| **404** | Not Found | Đường dẫn/tài nguyên mà client yêu cầu có tồn tại hoặc được ánh xạ không? | Sai URL, sai base path, không tìm thấy ID, static resource không tồn tại, functional route không match |
| **405** | Method Not Allowed | URL này có được phục vụ nhưng không chấp nhận method đang gửi không? | Gửi DELETE đến endpoint chỉ khai báo GET; path đúng nhưng method sai |
| **406** | Not Acceptable | Server có thể tạo một response phù hợp với **Accept** của client không? | Client đòi application/xml nhưng endpoint chỉ **produces application/json** |
| **415** | Unsupported Media Type | Server có chấp nhận định dạng **request body** theo **Content-Type** không? | POST text/plain vào endpoint chỉ **consumes application/json** |

Ghi nhớ bằng một câu: **404 xem URL; 405 xem method; 406 xem Accept; 415 xem Content-Type.** Đây là quy tắc điều tra đầu tiên, không phải khẳng định rằng mọi trường hợp trong mọi web framework đều phát đúng một status tự động.

### Bảng so sánh request và response

~~~text
HTTP request
  Method:       GET / POST / PUT / PATCH / DELETE ...
  Target:       /api/books/1
  Content-Type: định dạng BODY được GỬI lên (nếu có)
  Accept:       định dạng RESPONSE client muốn NHẬN
                  |
                  v
Spring MVC / Spring WebFlux handler mapping
                  |
                  +-- Không tìm thấy URL/tài nguyên -> thường 404
                  |
                  +-- URL phù hợp, method không được hỗ trợ -> 405
                  |
                  +-- Body media type không được chấp nhận -> 415
                  |
                  +-- Không có response representation phù hợp -> 406
                  |
                  v
Bind/decode request -> handler -> encode/write response
                  |
                  v
200 / 201 / 204 ... hoặc lỗi khác
~~~

Sơ đồ trên mô tả ý nghĩa logic, **không phải cam kết thứ tự kiểm tra nội bộ của từng HandlerMapping**. Nếu một request vi phạm nhiều điều kiện cùng lúc, status được chọn phụ thuộc cách router/handler matching xử lý điều kiện và exception resolver. Muốn chứng minh một lỗi, hãy tạo test mà **chỉ một điều kiện bị sai**.

## 2. Các điều kiện định tuyến của @RequestMapping

Một annotated controller có thể áp nhiều loại điều kiện:

~~~java
@PostMapping(
        path = "/books",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Book> create(@RequestBody CreateBookRequest request) {
    // ...
}
~~~

Trong ví dụ này:

- **path**: request phải nhắm tới /books (cộng với prefix của @RequestMapping cấp class và context/base path nếu có).
- **HTTP method**: request phải là POST.
- **consumes**: media type của request body phải tương thích application/json.
- **produces**: client phải chấp nhận media type response application/json.
- **@RequestBody**: sau khi chọn mapping, Spring cần đọc body và chuyển về kiểu CreateBookRequest qua message converter/codec.

Ngoài các điều kiện trên, @RequestMapping còn có **params**, **headers**, route versioning theo những phiên bản hỗ trợ, và các điều kiện tùy chỉnh. Sai params/headers không đồng nghĩa luôn có một status duy nhất; ví dụ Spring MVC có thể phản hồi 400 cho một request parameter condition không thỏa, trong khi route functional không match một predicate có thể dẫn tới 404.

**Cần phân biệt hai tầng lỗi:** (1) chưa tìm được handler phù hợp vì điều kiện mapping; (2) đã chọn handler nhưng thất bại khi đọc/ghi nội dung. Cả 406 và 415 có thể xuất hiện từ những tình huống liên quan tới điều kiện mapping hoặc khả năng xử lý media type sau đó.

### @RequestMapping ở cấp class và method

~~~java
@RestController
@RequestMapping("/api")
class BookController {

    @GetMapping(path = "/books/{id}", produces = "application/json")
    public Book find(@PathVariable("id") long id) {
        return new Book(id, "Demo");
    }
}
~~~

Ở đây URL là **/api/books/{id}**, không phải riêng /books/{id}. Với Spring MVC còn có thể có server.servlet.context-path; với Spring WebFlux reactive có thể có spring.webflux.base-path. Nếu client gọi URL ngoài ứng dụng thiếu prefix thì 404 hợp lý hơn việc điều tra JSON.

## 3. HTTP 404 Not Found: không có đích phù hợp hoặc không có tài nguyên

404 có ít nhất **hai nhóm nguyên nhân khác nhau**.

### 3.1. Không có handler cho URL được gửi

Ví dụ ứng dụng chỉ khai báo GET /api/books/1, nhưng client gọi:

~~~http
GET /api/book/1 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Đường dẫn /api/book/1 khác /api/books/1. Không có mapping tương ứng thì kết quả thường là 404.

Các tình huống thực tế:

- Sai chữ số nhiều/ít, dấu gạch ngang, viết hoa/thường hoặc path variable regex.
- Thiếu prefix /api/v1, server.servlet.context-path hoặc spring.webflux.base-path.
- Proxy/ingress strip path khác kỳ vọng.
- Gọi URL của actuator, static resource hoặc management port không đúng.
- Controller nằm ngoài vùng component scanning nên không được đăng ký.
- Định nghĩa route có điều kiện query/header mà request chưa thỏa; status chính xác còn phụ thuộc cơ chế handler mapping.

### 3.2. Route có tồn tại nhưng tài nguyên nghiệp vụ không tồn tại

GET /api/books/999 có thể match controller GET /api/books/{id}, nhưng không có sách với id=999. Service/controller **chủ động trả 404**:

~~~java
return repository.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
~~~

Đây là đoạn minh họa một repository đồng bộ có API Optional<Book>. Nó khác 404 do không có handler. Khi điều tra, phải phân biệt:

- **Routing 404**: controller chưa được gọi.
- **Business 404**: controller/service đã chạy và quyết định tài nguyên không tồn tại.

Thông tin log, tracing span, mapping registry và kết quả từ repository giúp xác định trường hợp nào.

### 3.3. Static resource 404

Trong Spring MVC, một đường dẫn không khớp controller có thể được xét bởi resource handler cho static content. Nếu file không tồn tại, response vẫn là 404; trên một số phiên bản Spring Framework, lỗi nội bộ có thể là **NoResourceFoundException** thay vì NoHandlerFoundException.

Vì vậy, thấy dòng log về static resource không có nghĩa một file CSS thật đã được yêu cầu; có thể request API sai đường dẫn đã đi vào cơ chế fallback resource handler.

**Không giải quyết 404 bằng cách tự thêm wildcard route /** trả 200 cho mọi request.** Cách đó có thể che lỗi API, làm hỏng monitoring và khiến client hiểu nhầm request thành công.

## 4. HTTP 405 Method Not Allowed: URL đúng, HTTP method sai

405 nghĩa là server biết target resource nhưng method hiện tại không được hỗ trợ. Trong Spring MVC annotated controllers, trường hợp điển hình:

~~~java
@GetMapping("/api/books/{id}")
public Book find(@PathVariable("id") long id) {
    return new Book(id, "Demo");
}
~~~

Request:

~~~http
DELETE /api/books/1 HTTP/1.1
Host: localhost:8080
~~~

Vì URL có GET mapping nhưng không có DELETE mapping, Spring MVC thường phản hồi **405 Method Not Allowed**. Theo HTTP semantics, response 405 phải có **Allow** header để nêu các method được hỗ trợ cho target resource.

Ví dụ phản hồi về mặt ý nghĩa:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
~~~

Giá trị chính xác của Allow (và các header khác) phải được kiểm tra từ response thật; Spring có hỗ trợ HEAD tương ứng GET, và việc xử lý OPTIONS hoặc cấu hình tùy chỉnh có thể thay đổi danh sách.

### 4.1. Những nhầm lẫn thường gặp

- **POST khác PUT và PATCH**: nếu controller chỉ có @PostMapping, client gọi PUT có thể nhận 405.
- **GET và HEAD**: Spring MVC và WebFlux hỗ trợ HEAD cho GET mappings; không nên dùng HEAD để chứng minh rằng chỉ có GET thì mọi method khác đều 405.
- **OPTIONS**: framework có xử lý OPTIONS và Allow tự động trong nhiều tình huống. CORS preflight OPTIONS còn đi qua CORS/security, nên một preflight lỗi không nhất thiết là lỗi mapping.
- **@RequestMapping không khai báo method** có thể cho phép nhiều HTTP methods; đừng giả định nó chỉ nhận GET.
- **Cổng đúng nhưng route khác**: nếu URL không match bất kỳ path nào, có thể trả 404 chứ không phải 405.

### 4.2. Kiểm tra và sửa

1. Đọc đúng method mà client thực sự gửi (proxy có thể đổi hoặc hạn chế method).
2. Đọc response header Allow nếu có.
3. Đối chiếu @GetMapping, @PostMapping, @PutMapping, @PatchMapping, @DeleteMapping và @RequestMapping(method=...).
4. Kiểm tra frontend fetch/axios, HTML form, API gateway hoặc ingress rule có dùng đúng method.
5. Tránh "sửa" bằng cách cho phép mọi method nếu hợp đồng API chỉ định rõ method.

Về phía client, sửa method cho đúng hợp đồng. Về phía server, bổ sung handler chỉ khi yêu cầu nghiệp vụ thực sự hỗ trợ thao tác đó.

## 5. HTTP 406 Not Acceptable: Accept không tương thích response

**Accept** là header của request mô tả **response representations** mà client muốn nhận. Nó không mô tả định dạng body request.

~~~http
GET /api/books/1 HTTP/1.1
Host: localhost:8080
Accept: application/xml
~~~

Nếu endpoint chỉ công bố:

~~~java
@GetMapping(
        path = "/api/books/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Book find(@PathVariable("id") long id) {
    return new Book(id, "Demo");
}
~~~

và không có mapping/representation khác phù hợp với application/xml, Spring có thể trả **406 Not Acceptable**. Trong điều kiện mapping của annotated controller, produces được so với Accept; ngoài matching, một response còn phải có writer/codec có thể serialize body thành loại dữ liệu đã chọn.

### 5.1. Vì sao 406 không giống 415?

- **406**: server không có **response format** phù hợp điều client chấp nhận.
- **415**: server không hỗ trợ **request body format** client đang gửi.

Một GET không có body vẫn có thể nhận 406 do Accept sai. Một POST JSON có Content-Type đúng nhưng Accept không tương thích response vẫn có thể nhận 406. Hai header phục vụ hai chiều khác nhau.

### 5.2. Accept có wildcard và quality value

Những giá trị thường gặp:

~~~http
Accept: application/json
Accept: application/* 
Accept: */*
Accept: application/json;q=0.9, text/plain;q=0.5
~~~

- */* chấp nhận các media types nói chung.
- application/* chấp nhận nhiều subtype dưới application/.
- q biểu diễn mức độ ưu tiên tương đối, không tự tạo thêm media type mà server chưa hỗ trợ.
- Một media type có q=0 được xem là không được chấp nhận cho lựa chọn tương ứng.

Khi client không gửi Accept hoặc gửi wildcard rộng, một endpoint chỉ produces JSON thường có thể trả JSON. Trong công cụ API như Postman/curl, cần quan sát **header gửi thật** thay vì đoán từ giao diện.

### 5.3. 406 có thể liên quan codec/message converter

Giả sử controller không khai báo produces nhưng trả object Java. Spring cần một HttpMessageConverter (MVC) hoặc HttpMessageWriter (WebFlux) để serialize object thành media type đã đàm phán. Nếu không có writer phù hợp với yêu cầu, framework có thể trả 406 hoặc lỗi serialization khác tùy giai đoạn và cấu hình.

Không nên vội thêm một @ExceptionHandler để đổi mọi 406 thành 200. Thay vào đó:

- Cập nhật Accept của client nếu hợp đồng response là JSON.
- Bổ sung representation XML hoặc text/plain chỉ khi API thực sự hỗ trợ.
- Bảo đảm dependency codec/converter có mặt và controller trả kiểu dữ liệu có thể serialize.
- Kiểm tra produces ở cấp class và method: một điều kiện produces ở method **ghi đè** điều kiện cấp class trong Spring mapping, không phải tự động cộng dồn.

## 6. HTTP 415 Unsupported Media Type: Content-Type của body không được hỗ trợ

**Content-Type** khai báo format của **request body được gửi lên**. Với POST JSON, header thông dụng là:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"Reactive Spring"}
~~~

Nếu endpoint yêu cầu JSON:

~~~java
@PostMapping(
        path = "/api/books",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public Book create(@RequestBody CreateBookRequest body) {
    return new Book(2, body.title());
}
~~~

thì request dùng **Content-Type: text/plain** mặc dù body nhìn giống JSON có thể bị từ chối bằng **415 Unsupported Media Type**.

Ví dụ request sai:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: text/plain
Accept: application/json

{"title":"Reactive Spring"}
~~~

Spring sử dụng consumes khi chọn annotated mapping và cần một reader/converter tương ứng để giải mã body. Trong một số tình huống, mặc dù mapping không khai báo consumes, việc thiếu HttpMessageConverter/HttpMessageReader phù hợp cũng có thể khiến ứng dụng phản hồi 415.

### 6.1. Thiếu Content-Type cũng có thể dẫn tới 415

Nếu endpoint chỉ chấp nhận application/json và request mang body nhưng không có Content-Type, Spring có thể không chấp nhận request. Cách xử lý phụ thuộc điều kiện mapping và reader/codec thực tế. Với API JSON, hãy khai báo Content-Type tường minh thay vì trông cậy vào suy đoán tự động.

### 6.2. JSON không hợp lệ thường là 400, không phải 415

Phân biệt hai request:

~~~text
A. Content-Type: text/plain
   Body: {"title":"Book"}
   -> Nếu endpoint chỉ consumes JSON, thường 415.

B. Content-Type: application/json
   Body: {"title": }
   -> Media type đã đúng, JSON sai cú pháp: thường 400 Bad Request.
~~~

**415 kiểm tra loại dữ liệu**, còn **400** thường liên quan cú pháp, thiếu/không hợp lệ dữ liệu hoặc binding/validation. Một request JSON đúng cú pháp nhưng thiếu field bắt buộc còn có thể trả 400/422 tùy hợp đồng validation của hệ thống.

### 6.3. Form và multipart không phải JSON

Những Content-Type khác nhau có cách decode khác nhau:

| Request body | Content-Type thường dùng | Cách xử lý phù hợp |
|---|---|---|
| JSON object | application/json | @RequestBody DTO qua JSON converter |
| Form URL encoded | application/x-www-form-urlencoded | @RequestParam / form binding phù hợp |
| Upload file | multipart/form-data; boundary=... | @RequestPart / MultipartFile ở MVC hoặc FilePart ở WebFlux |
| Text thuần | text/plain | @RequestBody String với mapping thích hợp |
| Binary stream | application/octet-stream | Resource, byte[] hoặc stream theo nhu cầu |

Nếu frontend gửi FormData, đừng ép Content-Type: application/json. Khi dùng multipart/form-data, trình duyệt thường tự tạo header kèm boundary; đặt thủ công thiếu boundary có thể gây lỗi phân tích request.

## 7. Chọn đúng Accept và Content-Type cho từng hành động

Đối với một REST API phục vụ JSON:

| Hành động | Content-Type request | Accept request | Tình huống |
|---|---|---|---|
| GET /api/books/1 | Thường không cần nếu GET không có body | application/json | Nhận sách dạng JSON |
| POST /api/books với JSON body | application/json | application/json | Tạo sách và nhận JSON |
| POST /api/books với text body | text/plain | application/json | Có thể nhận 415 nếu server chỉ consumes JSON |
| GET /api/books/1 | Không cần | application/xml | Có thể nhận 406 nếu server chỉ produces JSON |
| DELETE /api/books/1 | Thường không cần nếu không có body | */* | Có thể nhận 405 nếu chỉ GET được khai báo |

### 7.1. Những lỗi khi dùng curl

Để gửi JSON, dùng:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Book"}'
~~~

Trong shell Unix/Linux, lệnh trên hoạt động như mong muốn. Với Windows PowerShell, tùy phiên bản, lệnh curl có thể là alias của Invoke-WebRequest; nên dùng **curl.exe** để gọi executable curl và kiểm tra quy tắc quote của shell.

**Chú ý:** curl -d/--data có thể gửi Content-Type mặc định application/x-www-form-urlencoded nếu không đặt header khác. Vì vậy, chuỗi body nhìn như JSON không đồng nghĩa request đã có Content-Type JSON. Lệnh curl -i giúp xem status và response headers; curl -v giúp xem request headers đã gửi.

### 7.2. JavaScript fetch

~~~javascript
const response = await fetch("/api/books", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({ title: "Book" })
});

console.log(response.status);
~~~

Đây là ví dụ client, không phải file Java. Nó phân biệt rõ Content-Type cho body đi lên và Accept cho dữ liệu đi xuống. Nếu API nằm sau context path hoặc gateway, URL cần có prefix tương ứng.

## 8. Dự án Spring MVC chạy được: sinh đủ 404, 405, 406, 415

Ví dụ sau cố ý chỉ dùng **spring-boot-starter-web**, vì điều kiện mapping có thể được kiểm chứng bằng **MockMvc**. Spring WebFlux được so sánh ở các mục tiếp theo. Các class Java là mã đầy đủ cho một dự án Spring Boot MVC tối thiểu, không yêu cầu database.

Yêu cầu: JDK 17+, Maven, Spring Boot 3.5.0.

Cấu trúc:

~~~text
http-routing-status-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/routing/
    │   ├── RoutingDemoApplication.java
    │   ├── Book.java
    │   ├── CreateBookRequest.java
    │   └── BookController.java
    └── test/java/com/example/routing/
        └── BookRoutingTest.java
~~~

### 8.1. pom.xml

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
    <artifactId>http-routing-status-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
~~~

Maven parent quản lý các dependency versions tương thích với Boot. Khối plugin trên hợp lệ và cho phép chạy ứng dụng qua spring-boot:run hoặc đóng gói JAR.

### 8.2. RoutingDemoApplication.java

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

### 8.3. Book.java

~~~java
package com.example.routing;

public record Book(long id, String title) {
}
~~~

### 8.4. CreateBookRequest.java

~~~java
package com.example.routing;

public record CreateBookRequest(String title) {
}
~~~

### 8.5. BookController.java

~~~java
package com.example.routing;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> findById(
            @PathVariable("id") long id) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(new Book(1L, "Spring"));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> create(
            @RequestBody CreateBookRequest input) {

        if (input.title() == null || input.title().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        Book book = new Book(2L, input.title().trim());
        return ResponseEntity.created(
                URI.create("/api/books/" + book.id()))
                .body(book);
    }
}
~~~

Phân tích kết quả từ mapping:

- GET /api/books/1 + Accept application/json -> 200 và JSON.
- GET /api/books/999 + Accept application/json -> 404 **do business rule**.
- GET /api/does-not-exist -> 404 **do không có endpoint**, khi không có custom catch-all route.
- DELETE /api/books/1 -> 405 vì URL phù hợp GET mapping nhưng không có DELETE.
- GET /api/books/1 + Accept application/xml -> 406 vì endpoint chỉ produces application/json.
- POST /api/books + Content-Type text/plain -> 415 vì endpoint chỉ consumes application/json.
- POST /api/books + Content-Type application/json và JSON hợp lệ -> 201.
- POST /api/books + Content-Type application/json nhưng JSON sai cú pháp -> thường 400.

Ứng dụng lưu sách giả lập bằng object cố định. Không nên suy luận rằng POST thực sự lưu vào database hoặc GET /api/books/2 sẽ tự trả sách vừa tạo.

## 9. Test MockMvc: chứng minh từng mã lỗi

**src/test/java/com/example/routing/BookRoutingTest.java**

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookRoutingTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validGetReturnsJson() throws Exception {
        mvc.perform(get("/api/books/1")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.title").value("Spring"));
    }

    @Test
    void missingPathReturns404() throws Exception {
        mvc.perform(get("/api/does-not-exist"))
                .andExpect(status().isNotFound());
    }

    @Test
    void existingRouteButMissingEntityReturns404() throws Exception {
        mvc.perform(get("/api/books/999")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodReturns405AndAllowHeader() throws Exception {
        mvc.perform(delete("/api/books/1"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string(
                        HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void unacceptableResponseFormatReturns406() throws Exception {
        mvc.perform(get("/api/books/1")
                    .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void unsupportedRequestFormatReturns415() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Spring\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void validJsonPostReturns201() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Spring\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Spring"));
    }

    @Test
    void malformedJsonReturns400Not415() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"title\":"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Test có chủ đích **chỉ thay một điều kiện ở mỗi trường hợp**. Nhờ vậy, khi status không đúng kỳ vọng, dễ xác định phần URL/method/Accept/Content-Type cần sửa.

Chạy trong thư mục gốc dự án:

~~~bash
mvn test
mvn spring-boot:run
~~~

Khi test pass, Maven trả exit code 0. Số lượng log, thời gian và định dạng error body không được giả định cố định; tiêu chí QA là HTTP status, header cần thiết và dữ liệu business được assert.

### 9.1. Lệnh curl tương ứng

Chạy server cổng 8080 rồi thử:

~~~bash
# 404: URL không được định nghĩa
curl -i http://localhost:8080/api/does-not-exist

# 405: URL đúng nhưng method DELETE không được định nghĩa
curl -i -X DELETE http://localhost:8080/api/books/1

# 406: client chỉ muốn XML; server chỉ xuất JSON
curl -i http://localhost:8080/api/books/1 \
  -H 'Accept: application/xml'

# 415: body khai báo text/plain; server chỉ nhận JSON
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data '{"title":"Spring"}'

# 200: GET, URL và Accept đúng
curl -i http://localhost:8080/api/books/1 \
  -H 'Accept: application/json'

# 201: POST JSON đúng
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Spring"}'
~~~

Các câu lệnh trên dùng cú pháp shell Unix. Trên PowerShell, dùng curl.exe hoặc điều chỉnh quote. Không dùng lệnh GET với -d làm tình huống test khác đi ngoài ý định.

## 10. Khi cùng lúc sai nhiều điều kiện: tránh suy luận status tuyệt đối

Ví dụ:

~~~http
DELETE /api/books/1 HTTP/1.1
Accept: application/xml
Content-Type: text/plain
~~~

Request này vừa dùng method không được khai báo, vừa yêu cầu response XML và khai báo body type không phù hợp với endpoint POST. **Đừng kết luận chắc chắn nó phải trả 405, 406 hay 415 nếu chưa xét implementation.**

Spring MVC RequestMappingInfo đánh giá nhiều điều kiện để tìm mapping tốt nhất. Khi không có mapping đầy đủ, framework có thể kiểm tra thông tin partial matches để quyết định exception/status. Nếu xuất hiện custom HandlerMapping, custom exception resolver hoặc security filter, kết quả còn có thể khác.

Kỹ thuật điều tra hiệu quả là chia thành những bước độc lập:

1. Xác nhận URL GET/POST với Accept */* và body phù hợp.
2. Thử method sai nhưng giữ media type đúng.
3. Thử Accept sai nhưng method và URL đúng.
4. Thử Content-Type sai nhưng các điều kiện còn lại đúng.
5. Chỉ sau đó kiểm thử request cố ý sai nhiều điều kiện để xác nhận policy của hệ thống.

Đây cũng là lý do một integration test nên assert từng trạng thái riêng, không gom mọi lỗi thành một bài kiểm thử duy nhất.

## 11. Spring WebFlux annotated controllers: nguyên lý vẫn tương tự

Spring WebFlux hỗ trợ @GetMapping, @PostMapping, consumes và produces trong annotated controllers. Chúng cũng được dùng để match URL, HTTP method và media types; phần request/response body được xử lý bằng reactive codecs thay vì Servlet MVC HttpMessageConverters.

Ví dụ WebFlux controller **minh họa** (không đặt vào project MVC ở mục 8 nếu chưa đổi dependency và web application type):

~~~java
@RestController
@RequestMapping("/reactive/books")
public class ReactiveBookController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Book> get(@PathVariable("id") long id) {
        return Mono.just(new Book(id, "Reactive Spring"));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Book> create(@RequestBody Mono<CreateBookRequest> body) {
        return body.map(input -> new Book(2L, input.title()));
    }
}
~~~

Để sử dụng đoạn này cần import annotation từ org.springframework.web.bind.annotation, MediaType từ org.springframework.http và Mono từ reactor.core.publisher. Với ứng dụng WebFlux thực, cần spring-boot-starter-webflux và các class Book/CreateBookRequest. Đoạn trên không có validation nghiệp vụ; trong production cần bổ sung kiểm tra dữ liệu, status tạo mới và xử lý lỗi.

Các response code phổ biến trong WebFlux annotated route:

| Loại lỗi | Exception thường liên quan |
|---|---|
| Method không được hỗ trợ | org.springframework.web.server.MethodNotAllowedException |
| Không có representation phù hợp | org.springframework.web.server.NotAcceptableStatusException |
| Request body media type không được hỗ trợ | org.springframework.web.server.UnsupportedMediaTypeStatusException |
| Thiếu hoặc không hợp lệ dữ liệu đầu vào | ServerWebInputException hoặc các exception validation phù hợp |

Loại exception nội bộ có thể thay đổi theo vị trí lỗi và các extension được đăng ký; **HTTP status và API contract quan trọng hơn việc phụ thuộc chặt vào class exception của framework**.

### 11.1. WebTestClient

WebTestClient là lựa chọn phù hợp để test HTTP endpoint WebFlux:

~~~java
client.get()
        .uri("/reactive/books/1")
        .accept(MediaType.APPLICATION_XML)
        .exchange()
        .expectStatus().isNotAcceptable();

client.post()
        .uri("/reactive/books")
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue("not-json")
        .exchange()
        .expectStatus().isEqualTo(415);
~~~

Đây là đoạn minh họa trong phương thức test, giả định **client** là WebTestClient đã bind tới WebFlux application và class ReactiveBookController đã được đăng ký. Phần dependency/test setup khác với project MVC ở trên. Không ghép các đoạn này vào test MockMvc mà không chuyển sang reactive test fixture.

## 12. Trường hợp dễ nhầm: WebFlux.fn RouterFunction

WebFlux.fn định tuyến bằng RouterFunction và RequestPredicate, ví dụ:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/fn/books/{id}",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::get)
                .POST("/fn/books",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
~~~

Đây là đoạn minh họa yêu cầu các import WebFlux.fn, MediaType và biến handler với method phù hợp; không phải class Java đầy đủ. Hai predicate:

- accept(APPLICATION_JSON) **tham gia quyết định route có match không**.
- contentType(APPLICATION_JSON) **tham gia quyết định route có match không**.

**Khác biệt cực kỳ quan trọng:** nếu một functional route không match do predicate Accept hoặc Content-Type, RouterFunction có thể đơn giản trả kết quả "không có handler" để framework thử route kế tiếp. Nếu không route nào match, kết quả có thể là **404** thay vì tự động sinh **406** hoặc **415** giống partial match handling của annotated @RequestMapping.

Do đó không được khẳng định quy tắc:

~~~text
WebFlux.fn accept predicate sai -> luôn 406   (SAI)
WebFlux.fn contentType predicate sai -> luôn 415 (SAI)
~~~

Nếu API contract yêu cầu trả 406 hoặc 415 một cách nhất quán trong functional style, phải thiết kế chiến lược cụ thể: phân tách route matching khỏi kiểm tra representation trong handler, hoặc tạo fallback route/filter/error mapping chủ động trả status phù hợp. Cần test cả tình huống header không có, header không tương thích và route trùng pattern. Không bắt lỗi chung toàn ứng dụng rồi đổi mọi 404 thành 406/415.

### 12.1. Một handler functional chủ động trả 415

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    boolean json = request.headers().contentType()
            .map(type -> MediaType.APPLICATION_JSON.isCompatibleWith(type))
            .orElse(false);

    if (!json) {
        return ServerResponse.status(415).build();
    }

    return request.bodyToMono(CreateBookRequest.class)
            .flatMap(body -> ServerResponse.ok()
                    .bodyValue(new Book(2L, body.title())));
}
~~~

Đoạn minh họa chỉ biên dịch trong một class handler WebFlux.fn với import ServerRequest, ServerResponse, MediaType, Mono và DTO tương ứng. Nếu route **chỉ** dùng POST("/fn/books", handler::create) mà không ràng buộc contentType predicate trước đó, handler có cơ hội tự kiểm tra media type và trả 415. Trong production nên chuẩn hóa validation, 201/Location, error details và thống nhất behavior với các annotated endpoint.

Một route có predicate contentType từ chối request ngay ở bước định tuyến sẽ **không gọi** handler này, nên phải thiết kế router tương ứng nếu chọn chiến lược kiểm tra trong handler.

## 13. params và headers conditions không luôn cho 404

Spring MVC cũng cho phép:

~~~java
@GetMapping(path = "/search", params = "view=full")
public List<Book> search() {
    return List.of();
}
~~~

Nếu client gọi /search thiếu view=full, điều kiện mapping không thỏa. Trong Spring MVC, một trường hợp chỉ sai điều kiện request parameter có thể sinh **400 Bad Request** (ví dụ exception liên quan unsatisfied request parameter conditions), không nhất thiết là 404.

Tương tự, điều kiện:

~~~java
@GetMapping(path = "/search", headers = "X-Mode=full")
~~~

có thể làm route không match nếu header sai. Kết quả HTTP cuối cùng phụ thuộc điều kiện khác, handler mapping và exception handling.

Để diễn tả media types, dùng **consumes** và **produces** thay vì tự viết headers="Content-Type=..." hoặc headers="Accept=..." khi có thể. Hai thuộc tính chuyên dụng giúp Spring thực hiện media matching rõ nghĩa và đưa ra response code phù hợp hơn.

## 14. Phân biệt với những mã khác hay gặp

Đừng biến mọi request thất bại thành một trong bốn status của bài:

| Status | Tình huống thường gặp | Khác với 404/405/406/415 ra sao |
|---|---|---|
| **400 Bad Request** | JSON sai cú pháp, thiếu parameter, path variable sai kiểu, validation fail | Cú pháp hoặc dữ liệu request sai |
| **401 Unauthorized** | Chưa có credential hợp lệ | Authentication, không phải route không tồn tại |
| **403 Forbidden** | Có danh tính nhưng không đủ quyền, CSRF bị chặn | Authorization/security |
| **409 Conflict** | Trạng thái hiện tại xung đột với thao tác | Quy tắc nghiệp vụ |
| **413 Content Too Large** | Body vượt giới hạn upload/payload | Kích thước, không nhất thiết sai media type |
| **422 Unprocessable Content** | Dữ liệu có cú pháp đúng nhưng không xử lý được theo contract, nếu API chọn status này | Semantic validation |
| **500 Internal Server Error** | Lỗi code, serialization thất bại không được xử lý phù hợp | Sự cố phía server |
| **502/503/504** | Reverse proxy hoặc upstream gặp lỗi/timeout | Hệ thống phụ thuộc hoặc gateway |

Ví dụ controller có @GetMapping đúng nhưng Spring Security chặn request thì response có thể là 401/403 **trước** khi logic controller xử lý. Khi điều tra đừng loại bỏ lớp security hoặc proxy ra khỏi đường đi của request.

## 15. Quan sát và tìm nguồn gốc lỗi trong Spring Boot

Một quy trình có thể áp dụng:

1. **Ghi chính xác request:** method, full URL, request headers Accept/Content-Type, body và status/response headers.
2. **Xác nhận cổng, host, prefix:** server.port, server.servlet.context-path, spring.webflux.base-path, ingress rewrite.
3. **Xác nhận server stack:** ứng dụng đang dùng Spring MVC/DispatcherServlet hay Spring WebFlux/DispatcherHandler; đồng thời loại trừ nhầm lẫn MVC.fn/WebFlux.fn.
4. **Xem registered mappings:** annotation mapping path, method, consumes, produces; hoặc RouterFunction predicates và thứ tự.
5. **Xem lỗi xảy ra trước hay sau handler:** tracing, log theo correlation ID, exception type và việc controller có được gọi không.
6. **Kiểm tra message converters/codecs:** dependency Jackson JSON/XML, media types hỗ trợ, kiểu Java trả về, custom converter.
7. **Xem response headers:** Allow trong 405; Content-Type, Vary, Accept/Accept-Post nếu server gửi; không phụ thuộc hoàn toàn vào error body.
8. **Lập test đối chứng:** chỉ thay một điều kiện tại mỗi lần gọi.
9. **Xác minh error customizations:** @ControllerAdvice, @ExceptionHandler, ResponseEntityExceptionHandler, ErrorWebExceptionHandler, WebFilter hoặc Servlet Filter có can thiệp không.
10. **Thử cả app trực tiếp và qua gateway:** khi hai kết quả khác nhau, thường phải kiểm tra reverse proxy/security/gateway policies trước.

Có thể bật logging mức DEBUG cho handler mappings trong môi trường thử nghiệm, nhưng tránh log token, session cookie, body nhạy cảm hoặc thông tin khách hàng. Với Actuator, mapping endpoint có thể hỗ trợ quan sát registered mappings nếu dự án cài starter và cấu hình exposure/security phù hợp. Không bật công khai toàn bộ Actuator endpoint chỉ để điều tra một request.

### 15.1. Vì sao đổi Content-Type của response không sửa 415?

Vì 415 xảy ra ở **phía nhận request body**. Khi server chưa đọc được input hoặc chưa chọn được handler phù hợp, thay response Content-Type không giải quyết điều kiện consumes. Ngược lại, 406 là vấn đề chọn **định dạng trả về**, nên đổi Content-Type của request body có thể không tác động.

### 15.2. Vì sao cùng một URL lại trả 404 ở môi trường này và 405 ở môi trường kia?

Có thể do:

- Một môi trường có route mapping cùng path cho method khác, môi trường còn lại không đăng ký mapping nào.
- Reverse proxy strip prefix khác nhau nên actual target path thay đổi.
- Application context chưa scan một controller.
- Cấu hình route theo profile/feature flag.
- Sử dụng functional routing với predicate fail vs annotated mapping với partial match.
- Global exception handlers hoặc security filters thay đổi kết quả.

Tìm sự khác biệt trong **registered handler mappings và HTTP request thực tế**, không chỉ so sánh source code controller.

## 16. Hợp đồng lỗi API và Problem Details

Đối với public API, nên thống nhất cách biểu diễn lỗi cho client. Spring Framework hỗ trợ **ProblemDetail** theo RFC 9457; Spring Boot có các tùy chọn hỗ trợ Problem Details trong những phiên bản phù hợp.

Ví dụ một response lỗi có thể có:

~~~json
{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "Request body must use application/json",
  "instance": "/api/books"
}
~~~

Đây là **mẫu thiết kế**, không phải output mặc định cố định của Spring Boot 3.5.0. Error body, thông điệp, content type và trường instance phụ thuộc cấu hình và handler thực tế.

Lưu ý:

- Không tiết lộ stack trace, filesystem path, internal class name hoặc danh sách secret trong response.
- Thống nhất status HTTP thực với trường status bên trong body nếu có.
- Với 405, giữ header Allow đúng theo contract.
- Với 406, có thể giúp client biết response media types được hỗ trợ.
- Với 415, nêu định dạng request body được chấp nhận.
- Với business 404, cung cấp mã lỗi nghiệp vụ ổn định nhưng không tiết lộ sự tồn tại của tài nguyên bị hạn chế quyền.
- Không chuyển mọi 4xx thành 200 và nhét lỗi vào JSON body; cách đó phá HTTP semantics và khiến monitoring/caching sai.

## 17. Các anti-pattern cần tránh

**Anti-pattern 1: đổi tất cả 404 thành 200.** Điều này khiến frontend hoặc gateway nghĩ URL sai là thành công và gây khó khi vận hành.

**Anti-pattern 2: thêm @RequestMapping không giới hạn method chỉ để "chữa 405".** Nó mở những thao tác API chưa được thiết kế, có thể phá idempotency và security.

**Anti-pattern 3: xóa consumes để "chữa 415" mà không kiểm tra decoder.** Việc bỏ điều kiện không làm text/plain tự biến thành JSON; sau khi route match vẫn có thể thiếu reader/converter.

**Anti-pattern 4: đổi Accept thành */* ở mọi client để "chữa 406" mà không rõ API contract.** Biện pháp này có thể che sự bất nhất về response formats. Client nên khai báo representation nó thực sự xử lý được.

**Anti-pattern 5: tự đọc Accept/Content-Type bằng so sánh chuỗi chính xác.** Media types có thể có charset, parameters, wildcard và quality values. Dùng MediaType của Spring và cơ chế mapping/negotiation có sẵn.

**Anti-pattern 6: viết catch(Exception) trả 404 cho mọi lỗi.** JSON parse error, database timeout và permission denied cần status khác. 404 cho mọi sự cố khiến log/metrics đánh lừa người vận hành.

**Anti-pattern 7: giả định functional route predicates tự chuyển mọi mismatch thành 405/406/415.** RouterFunction thường dùng predicate để quyết định match; không có route cuối cùng có thể dẫn tới 404. Muốn status cụ thể phải thiết kế và kiểm thử.

## 18. Checklist kiểm thử trước khi release

- [ ] Đã xác nhận prefix/context path/ingress rewrite thực tế.
- [ ] Endpoint GET/POST/PUT/PATCH/DELETE có method contract rõ ràng.
- [ ] Có test 404 cho URL không tồn tại và tài nguyên nghiệp vụ không tồn tại (nếu API cần).
- [ ] Có test 405 khi dùng method không được hỗ trợ; kiểm tra Allow header phù hợp.
- [ ] Có test 406 khi Accept không tương thích với produces/response writer.
- [ ] Có test 415 khi Content-Type không tương thích với consumes/body decoder.
- [ ] Có test 400 với JSON không hợp lệ để không nhầm sang 415.
- [ ] Có test case hợp lệ 200/201 để xác nhận lỗi test không do route bị mất.
- [ ] Với WebFlux.fn, đã test predicate mismatch và fallback route/status một cách tường minh.
- [ ] Có integration test qua gateway hoặc reverse proxy nếu production dùng rewrite.
- [ ] Error body/correlation ID nhất quán, không lộ dữ liệu nhạy cảm.
- [ ] Không nhầm lỗi authentication/authorization với lỗi routing.

## 19. Ghi nhớ

**404**: không tìm được endpoint/path phù hợp hoặc tài nguyên cụ thể không tồn tại. **405**: target resource có phương thức khác nhưng method đang gửi không được hỗ trợ. **406**: không thể đáp ứng format response mà client yêu cầu qua Accept. **415**: không hỗ trợ format body client gửi qua Content-Type.

Trong Spring MVC/WebFlux annotated mappings, các thuộc tính path, method, consumes và produces giúp framework chọn handler và phản hồi status thích hợp. Trong WebFlux.fn, RequestPredicate không match có thể đơn giản khiến router trả kết quả "không tìm thấy route", nên cần tránh suy luận máy móc rằng sai Accept luôn ra 406 hay sai Content-Type luôn ra 415.

Để gỡ lỗi, hãy giữ nguyên URL, method, Accept và Content-Type trong log/test, rồi **chỉ đổi từng yếu tố một**. Bốn status này trở nên dễ hiểu khi tách rõ quá trình **tìm route → chọn method → xác minh request format → thương lượng response format → xử lý body**.

## Tài liệu tham khảo

- [Spring Framework — Mapping Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — Mapping Requests (Spring WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html)
- [Spring Framework — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Web MVC Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [MDN — HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status)
