# @RequestMapping ở lớp và phương thức; @GetMapping và @PostMapping trong Spring MVC

## 1. Mục tiêu: biến URL và HTTP method thành một điểm xử lý

Trong Spring MVC, một controller có thể cung cấp nhiều endpoint. **`@RequestMapping`** mô tả điều kiện để một HTTP request được giao cho controller method, chẳng hạn đường dẫn, HTTP method, query parameter, header, kiểu dữ liệu gửi vào và kiểu phản hồi. Các annotation **`@GetMapping`** và **`@PostMapping`** là dạng chuyên biệt, diễn đạt rõ một request dùng GET hay POST.

Sau bài học, bạn có thể:

- Đặt `@RequestMapping` ở **mức class** để khai báo prefix chung, rồi đặt `@GetMapping` hoặc `@PostMapping` ở **mức method** để khai báo endpoint cụ thể.
- Viết cú pháp tương đương bằng `@RequestMapping(method = RequestMethod.GET/POST)` và hiểu lý do ưu tiên annotation chuyên biệt.
- Phân biệt **URL path**, **HTTP method**, **URI variable**, **query parameter**, **request body** và các điều kiện `params`, `headers`, `consumes`, `produces`.
- Phân biệt một route được ánh xạ thành công với việc Spring đã chuyển tham số, gọi business code và tạo response.
- Xây ví dụ Java 17/Spring Boot MVC chạy được, xác minh bằng `curl` và `MockMvc`, nhận biết các tình huống 404, 405, 400, 406 và 415.

Phạm vi ở đây là **Spring MVC trên Servlet stack**. Spring WebFlux cũng có nhiều annotation giống tên, nhưng dùng web runtime reactive và cơ chế điều phối riêng. Bài học mô tả mapping của MVC; nó không yêu cầu kiến thức chi tiết về WebFlux.

## 2. Vị trí của mapping trong luồng xử lý MVC

Khi ứng dụng có `DispatcherServlet` hoạt động, luồng điển hình:

```text
Client gửi GET /api/books/42
                 |
           Servlet container
                 |
           DispatcherServlet
                 |
      RequestMappingHandlerMapping
      - HTTP method là GET?
      - Path /api/books/42 khớp?
      - Params, headers, consumes, produces khớp?
                 |
           chọn HandlerMethod
                 |
       RequestMappingHandlerAdapter
       - resolve @PathVariable, @RequestBody...
       - gọi controller method
                 |
       return value / message converters
                 |
           HTTP response
```

**`@RequestMapping` không trực tiếp gửi HTTP response.** Nó cung cấp metadata để `RequestMappingHandlerMapping` xác định handler method thích hợp. Sau khi chọn handler, `HandlerAdapter` mới chuẩn bị tham số, gọi method và xử lý kiểu trả về.

Ví dụ:

```java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{id}")
    public String byId(@PathVariable long id) {
        return "book:" + id;
    }
}
```

Đây là **fragment** (chưa có imports và ứng dụng chạy). Khi nhận `GET /api/books/42`, Spring kết hợp hai mapping thành một endpoint, lấy `id=42` và gọi `byId(42)`. Việc chuyển chuỗi `"42"` thành `long` thuộc giai đoạn resolve tham số, sau khi mapping đã xác định handler.

## 3. `@RequestMapping` tại mức class và mức method

### 3.1. Mức class: nhóm các endpoint cùng tiền tố

Đặt `@RequestMapping("/api/books")` lên class giúp mọi method bên trong có chung URL prefix, tránh lặp `/api/books`:

```java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping
    public String list() {
        return "list";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable String id) {
        return "book:" + id;
    }

    @PostMapping
    public String create() {
        return "created";
    }
}
```

Đây là **ví dụ riêng để đọc cú pháp**, không phải class của dự án hoàn chỉnh ở mục 8.

| Khai báo trên class | Khai báo trên method | HTTP endpoint kết quả |
| --- | --- | --- |
| `@RequestMapping("/api/books")` | `@GetMapping` | `GET /api/books` |
| `@RequestMapping("/api/books")` | `@GetMapping("/{id}")` | `GET /api/books/42` |
| `@RequestMapping("/api/books")` | `@PostMapping` | `POST /api/books` |

**Mức class không tự sinh ra handler.** Mặc dù class có prefix, chỉ các handler method đã được đăng ký đúng mới trở thành endpoint. Không có `@GetMapping` tại method thì việc khai báo prefix ở class không mặc nhiên tạo `GET /api/books`.

`@RequestMapping` ở mức class không bắt buộc: bạn có thể viết đường dẫn đầy đủ trên từng method. Nó đặc biệt hữu ích với một nhóm tài nguyên cùng prefix, chẳng hạn `/api/users` hoặc `/admin/reports`.

### 3.2. Mức method: xác định thao tác cụ thể

Ở mức method, có thể viết:

```java
@RequestMapping(path = "/{id}", method = RequestMethod.GET)
public String read(@PathVariable String id) {
    return id;
}
```

Hoặc ngắn gọn hơn:

```java
@GetMapping("/{id}")
public String read(@PathVariable String id) {
    return id;
}
```

Hai dạng này cùng biểu diễn HTTP GET cho `/{id}` trong cùng ngữ cảnh class. Tương tự:

```java
@RequestMapping(path = "", method = RequestMethod.POST)
public String create() {
    return "created";
}
```

Có thể viết:

```java
@PostMapping
public String create() {
    return "created";
}
```

Các đoạn đều là **method fragment đặt bên trong controller**, không phải Java file chạy độc lập.

### 3.3. Không khai báo HTTP method có ý nghĩa gì?

`@RequestMapping("/ping")` **không giới hạn** request vào GET hoặc POST. Spring MVC có thể khớp nhiều HTTP method cho mapping đó theo các điều kiện còn lại. Hành vi này có thể làm một endpoint vô tình chấp nhận thao tác ngoài ý muốn.

Ví dụ:

```java
@RequestMapping("/ping")
public String ping() {
    return "pong";
}
```

Đừng mặc định hiểu đó là “GET route”. Nếu mục đích là endpoint chỉ để đọc trạng thái, hãy dùng `@GetMapping("/ping")`. Nếu một method **thực sự** hỗ trợ nhiều HTTP method, khai báo tường minh:

```java
@RequestMapping(
    path = "/shared",
    method = {RequestMethod.GET, RequestMethod.POST}
)
public String shared() {
    return "shared";
}
```

Dùng nhiều method phải có chủ đích: GET được kỳ vọng có tính **safe/read-only**, còn POST thường dùng để yêu cầu xử lý một hành động hoặc tạo tài nguyên. Không nên dùng GET cho thao tác ghi/chuyển trạng thái chỉ vì URL tiện gọi.

## 4. `@GetMapping`: biểu diễn thao tác đọc

`@GetMapping` là composed annotation được xây dựng trên `@RequestMapping(method = RequestMethod.GET)`. Nó nhận phần lớn các thuộc tính mapping quan trọng như `path`/`value`, `params`, `headers` và `produces`.

Ví dụ:

```java
@GetMapping(path = "/{id}", produces = "application/json")
public Book getBook(@PathVariable("id") long id) {
    return new Book(id, "Java");
}
```

Khi dùng `@RestController` với JSON converter như Jackson, Spring có thể chuyển `Book` thành JSON. Các kiểu `@PathVariable` và record `Book` phải tồn tại phù hợp; snippet này không phải chương trình độc lập.

Những tính chất nên ghi nhớ:

- GET thường dùng để **truy xuất tài nguyên**. Theo HTTP semantics, GET là phương thức safe; thiết kế endpoint tránh cố ý thay đổi trạng thái hệ thống.
- `@GetMapping("/{id}")` khớp đường dẫn với **một segment** được capture vào `id`; biến đường dẫn không phải query parameter.
- HTTP GET có thể có `Accept` để lựa chọn định dạng phản hồi; `produces` mô tả những media type handler có thể tạo.
- Spring MVC còn hỗ trợ HTTP **HEAD** thông qua GET mapping: HEAD tương ứng metadata/header như GET nhưng không gửi response body.
- Với HTTP **OPTIONS**, Spring MVC thường có hỗ trợ tự tổng hợp các HTTP method hợp lệ thành header `Allow`; ứng dụng có thể tùy chỉnh hành vi này.

### 4.1. `@PathVariable` và `@RequestParam`

Hai request khác nhau:

```text
GET /api/books/42        -> id nằm trên URI path
GET /api/books?id=42     -> id là query parameter
```

Hai cách lấy dữ liệu:

```java
@GetMapping("/{id}")
public String byPath(@PathVariable("id") long id) {
    return "path:" + id;
}

@GetMapping(params = "id")
public String byQuery(@RequestParam("id") long id) {
    return "query:" + id;
}
```

Đây là các method trong controller có `@RequestMapping("/api/books")`. Chúng có **hai kiểu mapping khác nhau**. Trong ví dụ thứ hai, `params = "id"` tham gia bước **chọn handler**; `@RequestParam("id")` giải quyết việc **lấy và chuyển giá trị** sau đó.

Một `@GetMapping` với `@RequestParam` nhưng **không** thêm `params` vẫn có thể được chọn trước khi framework phát hiện thiếu tham số và trả lỗi binding. Phân biệt điều kiện tìm handler với điều kiện bắt buộc khi giải mã đối số.

### 4.2. Nhiều path cho cùng handler

Khi hai URL có cùng hành vi, có thể dùng array:

```java
@GetMapping(path = {"/status", "/health"})
public String status() {
    return "ok";
}
```

Đây là hai path trỏ cùng một method. Tuy nhiên, nhiều tên URL cho một tài nguyên có thể tạo thêm vấn đề tài liệu API/cache; chỉ sử dụng khi thật sự cần giữ alias hoặc khả năng tương thích.

## 5. `@PostMapping`: gửi dữ liệu để xử lý hoặc tạo tài nguyên

`@PostMapping` tương đương `@RequestMapping(method = RequestMethod.POST)`. POST thường được dùng khi client gửi body để server xử lý một hành động hoặc tạo tài nguyên mới.

Một ví dụ điển hình:

```java
@PostMapping(
    consumes = "application/json",
    produces = "application/json"
)
public ResponseEntity<Book> create(
        @RequestBody CreateBookRequest request) {
    Book created = service.create(request);
    return ResponseEntity
            .created(URI.create("/api/books/" + created.id()))
            .body(created);
}
```

Đoạn trên là **mã minh họa**, giả định có `service`, `Book`, `CreateBookRequest` và imports. Nó không chạy độc lập. Dự án hoàn chỉnh ở mục 8 thay thế `service` bằng kho lưu dữ liệu trong bộ nhớ để người học tự chạy.

Các phần mang ý nghĩa khác nhau:

| Phần | Vai trò |
| --- | --- |
| `@PostMapping` | Giới hạn handler vào HTTP POST |
| `consumes = "application/json"` | Điều kiện request `Content-Type` hỗ trợ JSON |
| `@RequestBody` | Đọc body, dùng message converter chuyển thành Java object |
| `produces = "application/json"` | Cho biết dạng response có thể trả |
| `ResponseEntity.created(uri)` | Trả **201 Created** với header `Location` |
| `body(created)` | Đưa representation của tài nguyên vừa tạo vào response body |

Không nhầm **`@PostMapping`** với **`@RequestBody`**: POST là HTTP method, còn `@RequestBody` chỉ định cách lấy dữ liệu đầu vào từ body. POST cũng có thể nhận form data hoặc multipart tùy controller; JSON không phải định dạng duy nhất.

Với hành động thành công, mã 200, 201 hay 204 tùy API contract. `@PostMapping` **không tự đặt status thành 201**: nếu trả Java object thông thường từ `@RestController` mà không cấu hình status, phản hồi thành công thường là 200. Dùng `@ResponseStatus(HttpStatus.CREATED)` hoặc `ResponseEntity.created(...)` nếu thật sự muốn 201.

## 6. Thuộc tính của `@RequestMapping` và các annotation chuyên biệt

| Thuộc tính | Dạng ví dụ | Dùng để |
| --- | --- | --- |
| `value` hoặc `path` | `"/books/{id}"` | Ghép đường dẫn HTTP |
| `method` | `RequestMethod.GET` | Giới hạn HTTP method; được ấn định bởi `@GetMapping`/`@PostMapping` |
| `params` | `"view=compact"`, `"!debug"` | Query parameter condition |
| `headers` | `"X-Client=mobile"` | Header condition |
| `consumes` | `"application/json"` | Media type mà handler chấp nhận từ request body |
| `produces` | `"application/json"` | Media type phản hồi mà handler có thể tạo |
| `name` | `"books.detail"` | Đặt tên mapping khi cần tham chiếu/quan sát |

**`value` và `path` là các alias** cùng biểu diễn phần đường dẫn, không phải hai prefix khác nhau. Với annotation chuyên biệt, `method` đã được cố định: không viết `@GetMapping(method = ...)` vì thuộc tính đó không tồn tại ở `@GetMapping`.

### 6.1. Kết hợp các điều kiện ở class và method

Thông thường, path ở class được kết hợp với path ở method, còn những điều kiện như HTTP method, params và headers được kết hợp theo ngữ nghĩa của `RequestMappingInfo` tương ứng. Riêng **`consumes` và `produces` ở method ghi đè khai báo tương ứng tại class**, không đơn giản cộng dồn.

Ví dụ:

```java
@RestController
@RequestMapping(
    path = "/api/documents",
    produces = "application/json"
)
public class DocumentController {

    @GetMapping("/{id}")
    public DocumentDto detail(@PathVariable long id) {
        return new DocumentDto(id, "doc");
    }

    @GetMapping(path = "/plain", produces = "text/plain")
    public String plain() {
        return "doc";
    }

    public record DocumentDto(long id, String name) {}
}
```

Đây là **class minh họa**, cần cấu hình Spring và JSON converter khi thực thi:

- `GET /api/documents/42`: method kế thừa `produces=application/json`.
- `GET /api/documents/plain`: method khai báo `produces=text/plain` nên **ghi đè** giá trị class.
- Pattern literal `/plain` thường cụ thể hơn `/{id}` khi cả hai có thể khớp.

Nếu khai báo hạn chế HTTP method ở class (ví dụ chỉ GET), các method cấp dưới không được tự ý mở rộng thành POST bằng `@PostMapping`; nên đặt prefix chung ở class, còn HTTP method riêng ở từng method để tránh sự nhầm lẫn.

### 6.2. Điều kiện `params`

```java
@GetMapping(path = "/reports", params = "view=compact")
public String compact() {
    return "compact";
}

@GetMapping(path = "/reports", params = "!view")
public String defaultView() {
    return "default";
}
```

Đây là **hai method cùng controller**:

- `GET /reports?view=compact` chọn `compact()`.
- `GET /reports` không có `view` chọn `defaultView()`.
- `GET /reports?view=full` không thỏa hai điều kiện trên; Spring có thể báo lỗi điều kiện parameter (thường là 400) tùy cấu hình và các mapping khác.

`params="debug"` đòi tham số hiện diện; `params="!debug"` đòi tham số vắng mặt; `params="mode=fast"` đòi giá trị cụ thể. Đây là **điều kiện routing**, không đồng nghĩa logic validate mọi giá trị trong đối số Java.

### 6.3. Điều kiện `headers`

```java
@GetMapping(
    path = "/client-info",
    headers = "X-Client=mobile"
)
public String mobileInfo() {
    return "mobile";
}
```

Handler chỉ khớp khi request có header `X-Client` theo điều kiện khai báo. Với `Content-Type` và `Accept`, nên dùng `consumes`/`produces` vì chúng mô tả media type rõ ràng hơn.

### 6.4. `Content-Type` khác `Accept`

| Header | Nói về | Điều kiện thường liên quan |
| --- | --- | --- |
| `Content-Type: application/json` | Định dạng **body mà client gửi lên** | `consumes="application/json"` |
| `Accept: application/json` | Định dạng **response client chấp nhận** | `produces="application/json"` |

Một request POST có JSON body thường cần `Content-Type` phù hợp để `@RequestBody` parse. Khi client yêu cầu dạng response không được hỗ trợ, điều kiện `produces` hoặc content negotiation có thể đưa tới HTTP 406. Khi media type body không được hỗ trợ, có thể đưa tới HTTP 415.

Không nên kết luận rằng cứ gửi `Accept: application/json` thì body của request là JSON: `Accept` và `Content-Type` giải quyết hai phía khác nhau.

## 7. So khớp URL và chọn method cụ thể

### 7.1. Literal, biến URI, wildcard

Giả sử trong cùng controller:

```java
@GetMapping("/featured")
public String featured() { return "featured"; }

@GetMapping("/{id}")
public String byId(@PathVariable String id) { return id; }
```

Với `GET /api/books/featured`, literal `/featured` được ưu tiên so với biến `/{id}` dù thứ tự khai báo trong file Java thế nào. Với `GET /api/books/42`, handler `/{id}` khớp.

Spring MVC 6.x mặc định sử dụng `PathPatternParser`. Một số cú pháp tiêu biểu:

- `/items/{id}`: capture một segment thành biến `id`.
- `/items/{id:[0-9]+}`: chỉ khớp segment số theo regex được khai báo.
- `/assets/*.png`: wildcard trong một segment.
- `/assets/**`: bắt nhiều segment ở **cuối** pattern.

Với `PathPatternParser`, `**` và `{*variable}` chỉ được đặt ở cuối pattern. Không sử dụng pattern kiểu `/a/**/b` như thể nó luôn hợp lệ.

### 7.2. Không dựa vào thứ tự method trong mã nguồn

Spring MVC chọn mapping dựa trên các request conditions và quy tắc so sánh độ cụ thể. Phương thức khai báo trước không tự động “thắng”. Nếu nhiều method có mapping thực chất giống nhau, ứng dụng có thể lỗi startup; nếu hai mapping khác nhau nhưng cạnh tranh mà không xác định được duy nhất handler, có thể gặp ambiguous handler methods.

Ví dụ **cố tình sai**, không ghép vào ứng dụng chạy ở mục 8:

```java
@GetMapping("/books/{id}")
public String one(@PathVariable String id) { return id; }

@GetMapping("/books/{id}")
public String two(@PathVariable String id) { return "other:" + id; }
```

Hai method có cùng mapping. Đổi tên Java method không sửa được xung đột: phải sửa API contract (đường dẫn, HTTP method hoặc một điều kiện khác có ý nghĩa).

### 7.3. Context path không nằm trong annotation

Khi deploy ứng dụng dưới context path `/catalog`:

```text
URL ngoài:   http://localhost:8080/catalog/api/books/42
Context path:                      /catalog
Class @RequestMapping:                    /api/books
Method @GetMapping:                                 /{id}
```

Controller không tự thêm `/catalog` vào `@RequestMapping`. Context path được xác định bởi deployment/HTTP server configuration. Nếu đặt cả prefix vào annotation, bạn có thể vô tình tạo URL sai.

### 7.4. Trạng thái trailing slash

Ở Spring MVC hiện đại, đừng giả định `/api/books` và `/api/books/` luôn được coi là cùng một path. Hành vi tùy phiên bản và cấu hình path matching. Nếu API cần hỗ trợ cả hai, quyết định rõ chính sách: redirect, định nghĩa alias, hoặc cấu hình phù hợp, và có test chứng minh.

## 8. Ví dụ hoàn chỉnh: GET và POST trên cùng tài nguyên

Ví dụ Java 17 + Spring Boot **3.3.5** dùng Spring MVC, embedded Tomcat và Jackson qua `spring-boot-starter-web`. Dữ liệu được lưu **trong bộ nhớ của controller** để dễ thử; restart ứng dụng sẽ làm mất các sách thêm sau khi chạy. Đây là ví dụ học tập, không mô hình persistence cho production.

### 8.1. Cấu trúc file

```text
book-routing-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/routing/
    │       ├── RoutingApplication.java
    │       └── BookController.java
    └── test/
        └── java/example/routing/
            └── BookControllerTest.java
```

### 8.2. Maven `pom.xml`

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>book-routing-demo</artifactId>
    <version>1.0.0</version>
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

Spring Boot parent quản lý các dependency version liên quan. Bạn cần JDK 17+ và Maven; các lệnh `mvn` dưới đây chạy trong thư mục có `pom.xml`. Không thêm `spring-boot-starter-webflux` để chạy ví dụ này.

### 8.3. Application entry point

File `src/main/java/example/routing/RoutingApplication.java`:

```java
package example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt auto-configuration/component scan. Vì controller nằm cùng package `example.routing`, Spring sẽ phát hiện bean khi ứng dụng khởi động.

### 8.4. Controller đầy đủ

File `src/main/java/example/routing/BookController.java`:

```java
package example.routing;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

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

    private final Map<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(2);

    public BookController() {
        books.put(1L, new Book(1L, "Java căn bản"));
        books.put(2L, new Book(2L, "Spring MVC"));
    }

    // GET /api/books
    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public List<Book> list() {
        return books.values().stream()
                .sorted(Comparator.comparingLong(Book::id))
                .toList();
    }

    // GET /api/books/featured
    @GetMapping(path = "/featured",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Book featured() {
        return books.get(1L);
    }

    // GET /api/books/{id}
    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> find(@PathVariable("id") long id) {
        Book book = books.get(id);
        return book == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(book);
    }

    // POST /api/books
    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> create(@RequestBody CreateBook request) {
        long id = nextId.incrementAndGet();
        Book book = new Book(id, request.title());
        books.put(id, book);

        return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(book);
    }

    public record Book(long id, String title) {}
    public record CreateBook(String title) {}
}
```

**Các route Spring đăng ký:**

| HTTP request | Handler method | Kết quả tiêu biểu |
| --- | --- | --- |
| `GET /api/books` | `list()` | Mảng JSON các sách, sắp xếp theo ID |
| `GET /api/books/featured` | `featured()` | JSON sách ID 1 |
| `GET /api/books/1` | `find(1)` | HTTP 200, JSON sách ID 1 |
| `GET /api/books/999` | `find(999)` | HTTP 404 do business không có sách |
| `POST /api/books` với JSON | `create(...)` | HTTP 201, `Location` và JSON sách mới |

Phân tích mapping:

- Prefix `/api/books` đến từ **class**, còn `/featured` và `/{id}` đến từ **method**.
- `@GetMapping` và `@PostMapping` phân biệt **hai hành vi trên cùng path `/api/books`**.
- `/featured` có độ cụ thể cao hơn `/{id}`; request không bị ép `"featured"` sang `long`.
- Với `/api/books/999`, handler **được tìm thấy** nhưng business method trả 404; khác lỗi không có route.
- `create` nhận JSON body qua `@RequestBody` rồi trả `201 Created` với `Location: /api/books/3` cho request tạo đầu tiên.
- `ConcurrentHashMap` và `AtomicLong` giúp ví dụ tránh lỗi truy cập dữ liệu cơ bản khi nhiều request tới cùng lúc; chúng **không** thay persistence, transaction, validation hoặc business rules thực tế.

### 8.5. Chạy ứng dụng và gửi request

Tại `book-routing-demo`, chạy test trước rồi bật web server:

```bash
mvn test
mvn spring-boot:run
```

Lệnh thứ hai giữ terminal chạy; mở một terminal khác. Với cấu hình mặc định và cổng 8080 còn trống, gửi:

```bash
curl -s http://localhost:8080/api/books
```

Body dự kiến:

```json
[{"id":1,"title":"Java căn bản"},{"id":2,"title":"Spring MVC"}]
```

Tìm theo ID:

```bash
curl -s http://localhost:8080/api/books/1
```

Body:

```json
{"id":1,"title":"Java căn bản"}
```

Xem đường dẫn literal `/featured`:

```bash
curl -s http://localhost:8080/api/books/featured
```

Body cũng là sách ID 1. Ví dụ này cho thấy Spring chọn `featured()` thay vì cố chuyển `featured` thành `long` cho `find(...)`.

Gửi POST tạo sách (cú pháp dòng lệnh POSIX):

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"HTTP và REST"}'
```

Phản hồi dự kiến có status và header (bỏ qua các header phụ thuộc server):

```http
HTTP/1.1 201
Location: /api/books/3
Content-Type: application/json

{"id":3,"title":"HTTP và REST"}
```

**ID 3** giả định đây là lần tạo sách đầu tiên kể từ khi khởi động. Nếu đã POST trước đó, `AtomicLong` tiếp tục tăng, nên ID khác. Dòng `Location` ở đây dùng path tương đối hợp lệ cho ví dụ; khi có gateway, context path, reverse proxy hoặc nhiều domain, cần chọn cách tạo URI theo deployment thật.

Sau đó:

```bash
curl -s http://localhost:8080/api/books/3
```

Body sau khi tạo lần đầu:

```json
{"id":3,"title":"HTTP và REST"}
```

Ví dụ không áp dụng bean validation cho trường `title`; production cần kiểm tra nội dung, độ dài, uniqueness, authorization và lưu trữ bền vững theo yêu cầu. Không copy kho in-memory làm tầng lưu trữ thật.

### 8.6. Cùng path, khác HTTP method

Hai endpoint này đều có **path `/api/books`**:

```text
GET  /api/books -> list()
POST /api/books -> create(...)
```

`GET /api/books` không tự gọi `create`; `POST /api/books` không tự gọi `list`. Nếu thử:

```bash
curl -i -X PUT http://localhost:8080/api/books
```

Trong demo, Spring MVC có path tương ứng nhưng không hỗ trợ PUT cho endpoint đó, nên kết quả thường là **405 Method Not Allowed**. Điều này khác **404 Not Found**, vốn thường biểu thị không có route phù hợp cho path hoặc business trả not-found.

Lưu ý `HEAD` có thể được hỗ trợ tự động khi đã có GET, và `OPTIONS` có thể được Spring xử lý theo các method đã đăng ký. Đừng liệt kê “chỉ GET/POST tuyệt đối” mà bỏ qua quy tắc HTTP infrastructure này.

## 9. Kiểm thử mapping bằng `MockMvc`

Thêm file `src/test/java/example/routing/BookControllerTest.java`:

```java
package example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void combinesClassAndMethodMappings() throws Exception {
        mvc.perform(get("/api/books/featured"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.title").value("Java căn bản"));

        mvc.perform(get("/api/books/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1));
    }

    @Test
    void postCreatesBookWithLocation() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"HTTP và REST\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/books/3"))
                .andExpect(jsonPath("$.id").value(3))
                .andExpect(jsonPath("$.title").value("HTTP và REST"));
    }

    @Test
    void rejectsUnsupportedHttpMethod() throws Exception {
        mvc.perform(put("/api/books"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

`@WebMvcTest(BookController.class)` tạo **MVC test slice**: kiểm tra controller, route resolution, message conversion và MVC configuration cần thiết, không cần khởi động một TCP HTTP server thật. `MockMvc` gửi request qua servlet testing pipeline và kiểm tra HTTP status, header, JSON response.

Vì chỉ test POST một lần trong class, ID đầu tiên được tạo dự kiến là 3. Với các test thực tế có nhiều thao tác ghi hoặc chạy song song, không nên dựa vào trạng thái chia sẻ giữa test methods; hãy cô lập trạng thái, mock service hoặc reset dữ liệu.

Chạy:

```bash
mvn test
```

Kỳ vọng ba test methods hoàn tất thành công nếu project được tạo đúng, dependency được tải và môi trường không can thiệp. Bài viết nêu **kết quả dự kiến theo code**, không khẳng định mọi máy đều đã chạy test thành công.

## 10. Các lỗi thường gặp khi dùng mapping

### 10.1. Gắn nhiều annotation mapping lên cùng một method

**Sai:**

```java
@GetMapping("/x")
@PostMapping("/x")
public String both() {
    return "x";
}
```

`@GetMapping` và `@PostMapping` đều là composed `@RequestMapping`. Spring không hỗ trợ dùng đồng thời nhiều annotation mapping như vậy trên **cùng một element**; có thể log warning và chỉ nhận một mapping. Muốn hỗ trợ GET lẫn POST, dùng `@RequestMapping(path="/x", method={RequestMethod.GET, RequestMethod.POST})`, hoặc tách thành hai method có contract riêng.

### 10.2. Nhầm class-level mapping tự tạo endpoint

`@RequestMapping("/api")` ở class chỉ là **metadata chung**. Cần có method tương ứng được Spring nhận diện; nếu class không phải controller bean hoặc thiếu method mapping, không có endpoint mong muốn.

### 10.3. Sai HTTP method

`@GetMapping("/save")` có thể cho phép client truy cập để “lưu” bằng GET, nhưng việc ghi dữ liệu qua GET vi phạm kỳ vọng safe HTTP và có thể gặp prefetch, cache hoặc crawler. Chọn `@PostMapping` cho tạo/thao tác xử lý mới, `@PutMapping` cho thay thế cập nhật, `@PatchMapping` cho cập nhật từng phần, `@DeleteMapping` cho xóa theo API contract.

### 10.4. Nhầm `@PathVariable` với `@RequestParam`

`/books/42` khác `/books?id=42`. Viết `@GetMapping("/{id}")` mà thử `/books?id=42` thì không tự thỏa path pattern. Phải định nghĩa một endpoint phù hợp với kiểu tham số thực tế.

### 10.5. Trùng mapping

Hai method cùng `@GetMapping("/api/books/{id}")` trong cùng handler registry có thể gây **ambiguous mapping khi ứng dụng khởi động**. Thay đổi tên Java method không đủ; cần phân biệt path, HTTP method hoặc điều kiện request có ý nghĩa.

### 10.6. 404 khác 405, 406 và 415

| Trạng thái | Khả năng điển hình | Kiểm tra |
| --- | --- | --- |
| 404 | Không có mapping cho path hoặc resource không tồn tại | Prefix class/method, context path, path variable, controller scan và code trả 404 |
| 405 | Path có handler mapping nhưng HTTP method không được chấp nhận | GET/POST/PUT/DELETE, `Allow` header |
| 406 | Client chỉ chấp nhận response media type khác `produces` | `Accept` và các message converter |
| 415 | Request body `Content-Type` không được hỗ trợ | `consumes` và các message converter |
| 400 | Sai body JSON, thiếu tham số bắt buộc, type conversion hoặc params condition | `@RequestBody`, `@RequestParam`, `@PathVariable`, nội dung request |
| 500 / startup failure | Đăng ký mapping trùng, lỗi bean hoặc code xử lý | Startup log và root cause |

Một HTTP status **không chứng minh duy nhất nguyên nhân**, vì exception handler, security và các tầng khác có thể thay đổi kết quả. Hãy quan sát cả request, mapping registry, converter và log server.

### 10.7. Mặc định trailing slash và path matching

`GET /api/books` không luôn được hiểu giống `GET /api/books/`. Spring 6.x thay đổi một số mặc định so với các thế hệ cũ. Nếu API cần cả hai dạng, kiểm thử rõ thay vì dựa vào thói quen của phiên bản trước.

### 10.8. Dùng `@RequestMapping` ở class với `method` quá hẹp

Ví dụ đặt `@RequestMapping(path="/api/books", method=GET)` trên class rồi viết `@PostMapping` trong class đó là thiết kế mâu thuẫn về HTTP method restriction. Cách phổ biến: class giữ **path prefix**, method quyết định GET/POST cụ thể.

### 10.9. Gắn mapping sai stack

Spring MVC và WebFlux có một số annotation cùng package, nhưng runtime điều phối khác nhau. Ví dụ dùng `spring-boot-starter-web` tạo MVC server thông thường, còn `spring-boot-starter-webflux` tạo reactive web stack nếu Boot cấu hình tương ứng. Chỉ thấy `@GetMapping` trong mã nguồn chưa đủ xác định là MVC hay WebFlux.

## 11. Những quy tắc thiết kế endpoint nên dùng

1. **Đặt prefix theo tài nguyên**: `/api/books`, `/api/orders` và chia các thao tác bằng HTTP method hoặc sub-resource path hợp lý.
2. **Dùng annotation chuyên biệt ở method**: `@GetMapping`, `@PostMapping`… để method constraint rõ ngay khi đọc code.
3. **Không đưa động từ vào GET để làm hành động ghi**: ví dụ `GET /createBook` là API contract dễ gây tác dụng phụ ngoài dự kiến.
4. **Trả HTTP status có ý nghĩa**: GET thành công thường 200; POST tạo tài nguyên thường 201 kèm `Location`; tài nguyên không tồn tại có thể 404; body/method không phù hợp có thể 400/405/415/406.
5. **Phân biệt routing và validation**: chọn handler dựa trên path/method/params/header/media type; sau đó validation của body và business rules được xử lý bởi các cơ chế tương ứng.
6. **Kiểm thử route chính và edge cases**: cùng path khác method, path literal cạnh path variable, media type mismatch, URI không hợp lệ, không tồn tại dữ liệu.
7. **Không tạo mapping quá rộng**: `/**` hoặc method-unrestricted mapping có thể vô tình nhận nhiều request; nên chủ động giới hạn.
8. **Tách nghiệp vụ khỏi controller trong dự án thật**: demo in-memory ở mục 8 để dễ quan sát; hệ thống vận hành nên dùng service/repository, transaction, validation và security thích hợp.

## 12. Bài tập và tự kiểm tra

### Bài 1 — dự đoán endpoint

Cho:

```java
@RestController
@RequestMapping("/students")
class StudentController {
    @GetMapping
    String all() { return "all"; }

    @GetMapping("/{id}")
    String one(@PathVariable String id) { return id; }

    @PostMapping
    String add() { return "created"; }
}
```

Hãy xác định handler cho `GET /students`, `GET /students/15`, `POST /students` và `PUT /students`. Đáp án: lần lượt `all()`, `one("15")`, `add()`; PUT không có handler hỗ trợ và thường nhận 405.

### Bài 2 — chuyển annotation

Viết lại `@RequestMapping(path="/products/{id}", method=RequestMethod.GET)` bằng annotation rút gọn. **Đáp án:** `@GetMapping("/products/{id}")`.

Ngược lại, viết `@PostMapping(path="/products", consumes="application/json")` thành `@RequestMapping`. **Đáp án:**

```java
@RequestMapping(
    path = "/products",
    method = RequestMethod.POST,
    consumes = "application/json"
)
```

Đây là **annotation fragment**, dùng trên method của controller.

### Bài 3 — phân tích request body

Một method `@PostMapping(consumes="application/json", produces="application/json")` nhận `@RequestBody`. Client gửi `Content-Type: text/plain` kèm chuỗi JSON. Vì sao chỉ có “văn bản trông giống JSON” là chưa đủ? **Gợi ý:** `consumes` kiểm tra media type của request, không chỉ kiểm tra các ký tự body.

### Bài 4 — literal và biến URI

Trong controller có `@GetMapping("/new")` và `@GetMapping("/{id}")`. Hãy giải thích vì sao `GET /new` thường chọn literal route, kể cả khi method cho biến `id` xuất hiện trước trong file.

### Bài 5 — cùng path GET và POST

Hãy thiết kế API nhỏ:

- `GET /notes`: đọc danh sách.
- `POST /notes`: nhận JSON và thêm một ghi chú.
- `GET /notes/{id}`: đọc một ghi chú.
- POST thành công: trả 201 và `Location`.

Sử dụng một `@RequestMapping("/notes")` ở class và annotation chuyên biệt trên ba method. Viết `MockMvc` test để chứng minh GET không gọi POST và POST không trả kết quả danh sách.

### Câu hỏi ghi nhớ

- **`@RequestMapping` đặt được ở đâu?** — Class và method; class thường cung cấp prefix/điều kiện chung, method bổ sung điều kiện endpoint.
- **`@GetMapping` khác `@RequestMapping` như thế nào?** — Là composed annotation chuyên biệt có `method=GET`.
- **`@PostMapping` có tự trả 201 không?** — Không; controller cần khai báo status hoặc trả `ResponseEntity` phù hợp.
- **Hai method có cùng path nhưng một GET một POST có hợp lệ không?** — Có, vì HTTP method là một phần điều kiện mapping.
- **`params` có giống `@RequestParam` không?** — Không; `params` giới hạn route, `@RequestParam` lấy/convert đối số khi handler được gọi.
- **`consumes` dựa vào header nào?** — Thông thường `Content-Type` của request.
- **`produces` liên quan header nào?** — `Accept` và cơ chế content negotiation của response.
- **Spring có chọn method theo vị trí dòng trong file không?** — Không; dựa trên request conditions và độ cụ thể.

## 13. Nguồn tham khảo chính thức

- Spring MVC Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring MVC Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/controller.html
- `@RequestMapping` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html
- `@GetMapping` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/GetMapping.html
- `@PostMapping` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/PostMapping.html
- `MockMvc`: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html

**Tóm điểm chính:** `@RequestMapping` ở class gom những đường dẫn và điều kiện chung; `@GetMapping`/`@PostMapping` ở method chỉ ra **hành động nào xử lý từng HTTP method**. Spring MVC kết hợp path, HTTP method và các điều kiện còn lại để chọn handler. Sau khi chọn xong, cơ chế binding, converter và controller code mới tạo response.
