# @RequestMapping trên interface và cách tổ chức hợp đồng controller

## 1. Mục tiêu và phạm vi

Trong Spring MVC, một controller thường dùng `@RestController` hoặc `@Controller` và khai báo `@RequestMapping`, `@GetMapping`, `@PostMapping` trực tiếp trên lớp/phương thức. Khi nhiều nhóm cùng phát triển API, ta có thể **đặt mô tả tuyến HTTP trên một Java interface**, để interface thể hiện hợp đồng HTTP và lớp controller chịu trách nhiệm thực thi.

Sau bài này, bạn có thể:
- Hiểu Spring MVC tìm mapping đặt trên interface như thế nào và vai trò của lớp triển khai.
- Thiết kế hợp đồng nhất quán về đường dẫn, HTTP method, tham số, body, media type và kiểu kết quả.
- Triển khai, chạy và kiểm thử controller chỉ đặt mapping trên interface.
- Nhận diện lỗi thường gặp khi trộn annotation, có nhiều implementation hoặc dùng AOP proxy.

Phạm vi là **Spring MVC (Servlet stack)** với Java 17+ và ví dụ Spring Boot 3.x / Spring Framework 6.x. Nguyên tắc về controller interface cũng áp dụng cho các phiên bản hiện đại khác, nhưng cấu hình proxy và cơ chế quét controller cần được kiểm thử theo phiên bản đang dùng.

## 2. Bản chất của `@RequestMapping` trên interface

`@RequestMapping` mô tả quy tắc ánh xạ một HTTP request tới handler method: `path`, `method`, `params`, `headers`, `consumes`, `produces`. Đặt ở mức kiểu để định nghĩa tiền tố/điều kiện chung, và đặt ở mức phương thức để xác định endpoint cụ thể. `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping` là các annotation tổ hợp dựa trên `@RequestMapping`.

Java interface có thể khai báo các annotation trên kiểu, phương thức và tham số:

~~~java
@RequestMapping("/api/books")
public interface BookApi {
    @GetMapping("/{id}")
    BookResponse get(@PathVariable("id") long id);
}
~~~

Điểm mấu chốt:
1. **Java interface quy định chữ ký phương thức** (tên, tham số, kiểu trả về), còn **Spring MVC diễn giải annotation trong phân cấp kiểu/phương thức** để tạo mapping. Không thể suy luận hành vi này chỉ từ quy tắc kế thừa annotation của Java hoặc từ `@Inherited`.
2. **Interface không tự trở thành controller bean** chỉ vì có `@RequestMapping`. Cần một lớp triển khai được Spring đăng ký, thường bằng `@RestController`.
3. Mapping trên interface không phải endpoint thứ hai. Với **một controller triển khai**, Spring đăng ký các handler method trên bean đó; request được định tuyến tới implementation tương ứng.
4. Interface là **hợp đồng HTTP ở tầng web**. Nó khác service interface (hợp đồng nghiệp vụ) và khác cơ chế tự tạo HTTP client; chỉ khai báo `@RequestMapping` không tự tạo client gửi request.

Sơ đồ xử lý rút gọn:

~~~text
BookApi (interface: @RequestMapping, @GetMapping, @PathVariable)
              │ implements
              ▼
BookController (@RestController: logic thực thi)
              │ component scan + handler detection
              ▼
RequestMappingHandlerMapping đăng ký GET /api/books/{id}
              │ request khớp path + HTTP method + điều kiện
              ▼
RequestMappingHandlerAdapter giải tham số → gọi BookController.get(...)
              │
              ▼
HttpMessageConverter ghi BookResponse thành JSON
~~~

Ở đây `RequestMappingHandlerMapping` dò controller và xây dựng `RequestMappingInfo`; `RequestMappingHandlerAdapter` thực thi handler. Trả về JSON trong ví dụ là nhờ `@RestController` (bao gồm `@ResponseBody`) và bộ chuyển đổi HTTP message phù hợp, chứ không do interface tự tạo JSON.

## 3. Hợp đồng HTTP cần thống nhất những gì?

| Thành phần | Đặt ở đâu trong interface | Ý nghĩa |
| --- | --- | --- |
| Tiền tố tuyến | `@RequestMapping("/api/books")` trên interface | Gom các endpoint dưới cùng tài nguyên |
| HTTP method + đường dẫn | `@GetMapping("/{id}")` / `@PostMapping` trên method | Tách thao tác đọc/tạo và tránh mapping quá rộng |
| Biến đường dẫn | `@PathVariable("id")` trên tham số | Gắn `{id}` trong URL với tham số Java |
| Query/header | `@RequestParam`, `@RequestHeader` nếu cần | Ràng buộc dữ liệu request |
| Request JSON | `@RequestBody` và `consumes = "application/json"` | Xác định dữ liệu vào, hỗ trợ chọn media type |
| Response JSON | `produces = "application/json"` | Xác định dạng phản hồi mà endpoint tạo ra |
| Mã trạng thái | `ResponseEntity<T>` hoặc `@ResponseStatus` | Nêu rõ kết quả thành công và các tình huống lỗi |

Một mapping ở mức kiểu kết hợp với mapping ở mức phương thức (ví dụ `/api/books` + `/{id}` thành `/api/books/{id}`). Các thuộc tính không phải lúc nào cũng “cộng dồn” giống `path`: chẳng hạn `consumes` và `produces` ở method có thể **ghi đè** điều kiện tương ứng ở type. Vì vậy nên xác định rõ điều kiện thực tế bằng kiểm thử.

### Vì sao gom annotation vào một chỗ?

Nếu interface khai báo `@GetMapping` nhưng implementation tự thêm `@PostMapping` hoặc thay `@RequestMapping`, mỗi nơi lại mô tả một phần hợp đồng. Điều đó làm tăng rủi ro mapping không như mong đợi, phụ thuộc việc Spring hợp nhất annotation trong phân cấp kiểu và cách proxy trình bày type tại runtime. **Quy ước an toàn: khi đã chọn controller interface, đặt nhất quán các annotation mapping (và annotation hợp đồng liên quan như `@SessionAttributes` nếu sử dụng) trên interface; implementation chủ yếu giữ `@RestController` và logic xử lý.**

Cũng không đặt `@RequestMapping` và `@GetMapping` cùng trên **cùng một phương thức** như hai mapping độc lập. Chúng cùng thuộc họ mapping annotation; Spring cảnh báo và có thể chỉ sử dụng annotation đầu tiên.

## 4. Ví dụ đầy đủ: contract → controller → HTTP request

Giả sử đã tạo ứng dụng Spring Boot 3.x dùng Java 17+, có dependency `spring-boot-starter-web` và `spring-boot-starter-test` (cho phần kiểm thử). Ví dụ dưới đây dùng bộ nhớ tạm để tập trung vào request mapping, không phụ thuộc database.

Cấu trúc tệp:

~~~text
src/main/java/com/example/demo/
├── DemoApplication.java
├── api/
│   ├── BookApi.java
│   ├── BookResponse.java
│   └── CreateBookRequest.java
└── web/
    └── BookController.java
src/test/java/com/example/demo/web/
└── BookControllerMappingTest.java
~~~

### 4.1. Interface định nghĩa hợp đồng

`src/main/java/com/example/demo/api/BookApi.java`

~~~java
package com.example.demo.api;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping(path = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
public interface BookApi {

    @GetMapping("/{id}")
    ResponseEntity<BookResponse> get(@PathVariable("id") long id);

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(@RequestBody CreateBookRequest input);
}
~~~

- `@RequestMapping` ở interface xác định tiền tố `/api/books` và response JSON dùng chung.
- `@GetMapping("/{id}")` chỉ nhận GET, lấy `id` từ URL; đặt tên rõ trong `@PathVariable("id")` để không phụ thuộc việc Java compiler có giữ tên tham số hay không.
- `@PostMapping` chỉ nhận POST tại `/api/books`; `consumes` yêu cầu `Content-Type: application/json`.
- `ResponseEntity` cho phép implementation quyết định status và body (ví dụ `200`, `201`, `404`), không trộn logic trạng thái với chữ ký interface.

### 4.2. DTO cho request và response

`src/main/java/com/example/demo/api/BookResponse.java`

~~~java
package com.example.demo.api;

public record BookResponse(long id, String title) {}
~~~

`src/main/java/com/example/demo/api/CreateBookRequest.java`

~~~java
package com.example.demo.api;

public record CreateBookRequest(String title) {}
~~~

Java record phù hợp với DTO ngắn, dữ liệu bất biến. Spring Boot 3.x (với Jackson từ web starter) có thể chuyển JSON tương ứng sang/từ các record này.

### 4.3. Implementation: không lặp lại mapping

`src/main/java/com/example/demo/web/BookController.java`

~~~java
package com.example.demo.web;

import com.example.demo.api.BookApi;
import com.example.demo.api.BookResponse;
import com.example.demo.api.CreateBookRequest;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController implements BookApi {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookResponse> books = new ConcurrentHashMap<>();

    @Override
    public ResponseEntity<BookResponse> get(long id) {
        BookResponse book = books.get(id);
        return book == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(book);
    }

    @Override
    public ResponseEntity<BookResponse> create(CreateBookRequest input) {
        long id = nextId.incrementAndGet();
        BookResponse book = new BookResponse(id, input.title());
        books.put(id, book);
        return ResponseEntity.status(HttpStatus.CREATED).body(book);
    }
}
~~~

Lớp này có `@RestController` để được quét thành web bean và trả response body; các method `get` và `create` **không cần lặp `@GetMapping`, `@PostMapping`, `@RequestBody` hay `@PathVariable`**. Spring MVC nhận metadata request từ interface đã triển khai. `@Override` là kiểm tra của Java compiler, giúp phát hiện implementation sai chữ ký hợp đồng.

`ConcurrentHashMap` và `AtomicLong` chỉ tạo một ví dụ có thể gọi nhiều request, không đại diện cho cách lưu dữ liệu production. Bản demo không ràng buộc `title` phải khác `null` hoặc khác chuỗi rỗng; nếu cần validation, thêm Bean Validation (`@Valid`, constraint của Jakarta và `spring-boot-starter-validation`) cùng xử lý lỗi thích hợp.

### 4.4. Ứng dụng khởi chạy

`src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` nằm ở package cha `com.example.demo`, nên component scan thấy `web.BookController`. Điều này tránh lỗi tạo interface đúng nhưng ứng dụng không phát hiện implementation.

Ví dụ các dependency cần có trong Gradle project Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Phần dependency giả định dự án đã cấu hình Spring Boot plugin, repository Maven Central và Java toolchain. Chạy tại thư mục dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Thử API bằng bash/WSL/macOS terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"title":"Spring MVC"}'
curl -i http://localhost:8080/api/books/1 -H 'Accept: application/json'
curl -i http://localhost:8080/api/books/999 -H 'Accept: application/json'
~~~

Nếu ứng dụng mới chạy với bộ nhớ trống và không có request tạo sách nào khác chen vào, response dự kiến lần lượt:

~~~text
POST /api/books          -> 201 Created, body {"id":1,"title":"Spring MVC"}
GET  /api/books/1        -> 200 OK,      body {"id":1,"title":"Spring MVC"}
GET  /api/books/999      -> 404 Not Found
~~~

Status và body trên là kết quả đáng tin của code mẫu; thứ tự header, format lỗi HTTP và log phụ thuộc cấu hình runtime. Gửi POST sai `Content-Type` (ví dụ `text/plain`) có thể nhận `415 Unsupported Media Type` vì điều kiện `consumes` không phù hợp; dùng phương thức không được khai báo cho cùng path thường nhận `405 Method Not Allowed`.

## 5. Kiểm chứng mapping bằng MockMvc

`src/test/java/com/example/demo/web/BookControllerMappingTest.java`

~~~java
package com.example.demo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerMappingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void interfaceMappingIsUsedByController() throws Exception {
        mockMvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Spring MVC\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.title").value("Spring MVC"));

        mockMvc.perform(get("/api/books/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring MVC"));

        mockMvc.perform(get("/api/books/999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());

        mockMvc.perform(delete("/api/books/1"))
                .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Chạy `./gradlew test` trong project đã có cấu hình test JUnit Platform thích hợp. Test không gắn annotation mapping tại implementation mà vẫn yêu cầu route hoạt động, vì thế nó xác nhận chính việc **Spring đọc interface metadata**. Với dự án có Spring Security hoặc global MVC configuration bổ sung, cần thiết lập test slice phù hợp (chẳng hạn cấu hình authentication hoặc mock) để kết quả không bị ảnh hưởng bởi filter ngoài ví dụ.

Thêm các ca kiểm tra theo hợp đồng thực tế: path variable không hợp lệ, thiếu body, `Content-Type` sai, `Accept` không hỗ trợ, query/header bắt buộc và status lỗi. Sau khi nâng cấp Spring, kiểm tra lại registration bằng test hoặc Spring Boot Actuator `/actuator/mappings` (chỉ khi đã bật actuator và cho phép endpoint đó).

## 6. Tổ chức package và trách nhiệm

Một cấu trúc thực tế với API nhỏ có thể là:

~~~text
com.example.catalog
├── api/                 # HTTP contract và DTO request/response
│   ├── BookApi.java
│   └── dto/...
├── web/                 # @RestController implements BookApi, chuyển đổi lỗi HTTP
│   └── BookController.java
├── application/         # Use case/service, logic nghiệp vụ
│   └── BookService.java
└── domain/              # Entity/value object, quy tắc nghiệp vụ
~~~

Hợp đồng `BookApi` nên mô tả **điều client HTTP quan sát được**: route, method, request/response shape, mã trạng thái và ràng buộc giao tiếp cần thiết. `BookController` nhận request, gọi service và chuyển đổi kết quả sang HTTP. `BookService` không cần biết `@GetMapping` hay Servlet API.

Nếu chia API contract sang module thư viện, module triển khai phải có dependency chứa interface và DTO; module web cần dependency Spring MVC để dùng annotation. Không nhất thiết phải tạo module riêng cho ứng dụng nhỏ: lợi ích của hợp đồng là rõ ranh giới và tái sử dụng, nhưng phải cân nhắc số lượng tệp/phụ thuộc phát sinh.

**Quy tắc thay đổi:** sửa `/api/books/{id}`, đổi `@PathVariable`, thêm required header hoặc đổi DTO đều là thay đổi hợp đồng HTTP, có khả năng ảnh hưởng client và test. Cần cập nhật tài liệu API, kiểm thử tích hợp và chính sách tương thích. Không coi việc đổi tên Java method (khi route và chữ ký tương thích) là tương đương đổi HTTP endpoint.

## 7. Trường hợp AOP proxy: lỗi dễ bỏ sót

AOP (ví dụ advice từ `@Transactional` hoặc custom aspect) có thể tạo proxy bao quanh controller. Có hai kiểu phổ biến:

| Kiểu proxy | Cách nhìn thấy controller | Điểm cần chú ý |
| --- | --- | --- |
| Class-based proxy (CGLIB) | Proxy dựa trên lớp controller | Thường phù hợp hơn với controller có interface và annotation ở interface; lưu ý hạn chế của lớp/method `final` |
| Interface-based proxy (JDK dynamic proxy) | Proxy phơi ra interface | Khả năng phát hiện controller và annotation chịu ảnh hưởng kiểu proxy và phiên bản Spring |

**Cảnh báo phiên bản:** kể từ Spring Framework 6.0, khi dùng *interface-based proxy*, Spring MVC **không còn nhận diện controller chỉ dựa vào `@RequestMapping` ở mức type trên interface**. Tài liệu Spring khuyến nghị dùng **class-based proxy** hoặc, nếu phải dùng interface proxy, interface phải có thêm `@Controller`. Đây là trường hợp cụ thể về *controller detection*, không đồng nghĩa mọi `@RequestMapping` trên interface ngừng hoạt động trong Spring 6.

Trong ứng dụng thông thường, hãy giữ `@RestController` ở lớp implementation và ưu tiên đặt transaction ở service. Nếu có AOP trực tiếp trên controller và endpoint bỗng `404` sau khi thêm advice, kiểm tra kiểu proxy, annotation controller, component scan và kết quả đăng ký mapping. Khi đổi cơ chế proxy, chạy lại MockMvc/smoke test thay vì chỉ dựa vào Java compiler.

## 8. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `404` cho mọi route dù có `BookApi` | Chưa có bean triển khai, controller nằm ngoài component scan, hoặc gặp proxy detection | Đảm bảo implementation có `@RestController`, quét đúng package, kiểm tra proxy/mappings |
| `404` riêng một URL | Sai tiền tố type-level, path variable hay context path | Đối chiếu `@RequestMapping` interface với `@GetMapping` và request URL |
| `405 Method Not Allowed` | URL có mapping nhưng HTTP method không phù hợp | Dùng `@GetMapping`/`@PostMapping` chính xác và gửi đúng method |
| `415 Unsupported Media Type` | `Content-Type` không thỏa `consumes` | Gửi JSON đúng content type hoặc sửa hợp đồng có chủ đích |
| `406 Not Acceptable` | `Accept` không tương thích `produces` | Đối chiếu media type, message converter và Accept |
| `400` khi bind tham số | Tên `@PathVariable` không khớp hoặc JSON sai shape/kiểu | Đặt tên tường minh, kiểm tra DTO và body |
| Startup báo ambiguous mapping | Hai controller cùng đăng ký path, method và điều kiện trùng nhau | Chỉ có một owner của mỗi endpoint hoặc thiết kế route khác nhau rõ ràng |
| Annotation không như dự tính | Trộn mapping giữa interface/implementation hoặc khai báo nhiều mapping annotation trên một phần tử | Dồn hợp đồng ở interface, loại bỏ annotation mapping trùng và viết test |
| Documentation/codegen thiếu endpoint | Công cụ sinh tài liệu không đọc annotation trong hierarchy giống Spring MVC | Kiểm tra cấu hình và phiên bản công cụ, so tài liệu với mapping runtime |

Không khắc phục `404` bằng cách sao chép mọi annotation xuống implementation trước khi kiểm tra component scan/proxy: làm vậy khiến hợp đồng nằm hai nơi và dễ phát sinh sai lệch.

### Hai implementation của cùng một interface có dùng chung route được không?

Về cú pháp Java, nhiều lớp có thể `implements BookApi`. Nhưng khi **cả hai đều là controller bean** với cùng mapping HTTP, Spring MVC có thể báo ambiguous mapping lúc khởi tạo vì nhiều handler cùng nhận một request. Nếu cần hai phiên bản hoặc hai kênh API, hãy thiết kế **đường dẫn/điều kiện mapping tách biệt ngay ở contract**, hoặc chỉ đăng ký một implementation theo profile/condition phù hợp; không giả định Spring tự chọn implementation giống dependency injection.

### Có nên dùng interface cho mọi controller?

Không bắt buộc. Với một controller đơn giản, đặt `@GetMapping` trực tiếp trên lớp có thể dễ đọc hơn. Interface phát huy giá trị khi cần hợp đồng chung giữa đội API và đội triển khai, kiểm soát thay đổi, sinh tài liệu/kiểm thử theo hợp đồng hoặc chia package/module. Tránh tạo interface chỉ để lặp lại nguyên xi từng method mà không có nhu cầu ranh giới rõ ràng.

### Khác gì `@HttpExchange`?

`@HttpExchange` cùng các annotation như `@GetExchange` có thể định nghĩa HTTP interface để Spring tạo proxy **client**; Spring MVC cũng hỗ trợ các contract này trong một số tình huống server. Tuy nhiên `@RequestMapping` là hợp đồng mapping linh hoạt phía server với tập điều kiện đầy đủ hơn. Không suy luận rằng `BookApi` có `@GetMapping` sẽ tự tạo HTTP client, và không đổi sang `@HttpExchange` chỉ vì muốn tách hợp đồng controller.

## 9. Checklist khi thiết kế hợp đồng controller

1. Xác định interface phục vụ HTTP boundary nào và ai sở hữu từng endpoint.
2. Đặt tiền tố `@RequestMapping` trên interface; dùng annotation theo HTTP method cụ thể cho từng operation.
3. Ghi tường minh tên biến `@PathVariable`/`@RequestParam` khi có giá trị học tập/vận hành; định nghĩa request/response DTO ổn định.
4. Đặt toàn bộ mapping metadata nhất quán trên interface; lớp `@RestController` triển khai logic mà không lặp mapping.
5. Kiểm tra controller bean được scan, chỉ có một mapping chủ sở hữu, và AOP không làm mất controller detection.
6. Viết MockMvc test cho route, verb, body/media type, response status và các tình huống lỗi quan trọng.
7. Khi thay hợp đồng, xem đó là thay đổi API cần review tương thích và tài liệu.

**Ghi nhớ:** interface nêu “HTTP request nào được nhận và contract ra sao”; implementation nêu “xử lý thế nào”. Spring MVC kết nối hai phần bằng việc tìm mapping annotation trong phân cấp controller. Ranh giới này hữu ích khi được giữ nhất quán và luôn có kiểm thử chạy qua HTTP dispatcher thực tế.

## 10. Tài liệu tham khảo

- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `@RequestMapping`, tổ hợp mapping, điều kiện request, `@HttpExchange`.
- [Spring Framework — Controller Declaration / AOP Proxies](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html): đăng ký controller, lưu ý proxy từ Spring 6.0.
- [Spring Framework — Handler Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods.html): chữ ký handler, parameter/return handling.
- [`@RequestMapping` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): khuyến nghị nhất quán mapping annotation khi dùng controller interfaces.
