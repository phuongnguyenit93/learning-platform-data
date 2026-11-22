# ResponseEntity: điều khiển status, header và body trong Spring MVC

> **Phạm vi:** Spring Web MVC (Servlet stack), ví dụ Java 17+ với Spring Boot 3.x/Spring Framework 6.x. Chủ đề chính là `org.springframework.http.ResponseEntity<T>`: một kiểu trả về của controller biểu diễn **mã trạng thái HTTP, tập header và body** trong cùng một giá trị. Bài viết hướng dẫn các builder method, HTTP semantics, content negotiation, xử lý tài nguyên thành công/thất bại, response không body, file và cache, rồi áp dụng vào một REST controller chạy được.

## 1. Vì sao REST endpoint cần kiểm soát toàn bộ response?

Một API không chỉ gửi dữ liệu JSON; nó còn cần nói cho client biết thao tác **đã thành công, tạo tài nguyên mới, không tìm thấy, đã xóa hay yêu cầu sửa lại**. HTTP response có ba phần quan trọng:

```http
HTTP/1.1 201 Created
Location: /api/books/11
Content-Type: application/json
X-Resource-Type: book

{"id":11,"title":"Clean Code","author":"Robert Martin"}
```

- **Status** `201 Created`: cho biết server đã tạo tài nguyên.
- **Header** `Location`: cung cấp URI tài nguyên vừa tạo. `Content-Type` mô tả định dạng body; các header khác bổ sung metadata.
- **Body**: nội dung tài nguyên hoặc thông báo lỗi, có thể không tồn tại tùy trường hợp.

Nếu method đơn thuần trả `Book` từ `@RestController`, Spring thường trả `200 OK` và serialize object thành JSON qua converter. Điều đó tốt cho GET đơn giản, nhưng chưa biểu đạt đủ các trường hợp `201`, `204`, `404`, custom headers hoặc cache semantics.

**`ResponseEntity<T>` gom cả ba thành phần thành một giá trị return rõ ràng.** Nó kế thừa `HttpEntity<T>` (chứa headers và body) và bổ sung status. Trong Spring MVC, body thường được ghi bằng `HttpMessageConverter` thích hợp; `ResponseEntity` không tự serialize JSON bằng cách ghép chuỗi.

## 2. Bắt đầu với cú pháp cơ bản

```java
@GetMapping("/hello")
public ResponseEntity<String> hello() {
    return ResponseEntity.ok("Xin chào");
}
```

Trong `@RestController`, ví dụ trả `200 OK` với body chuỗi `Xin chào`. Dữ liệu có thể là `String`, DTO, `List<Dto>`, `byte[]`, `Resource` hoặc kiểu khác được một converter hỗ trợ.

Ba cách tạo cùng mục tiêu status + headers + body:

```java
// 1. Builder API: thường dễ đọc nhất.
ResponseEntity<String> first = ResponseEntity
        .status(HttpStatus.ACCEPTED)
        .header("X-Job-Id", "j-42")
        .body("queued");

// 2. Constructor: hữu ích khi đã có HttpHeaders.
HttpHeaders headers = new HttpHeaders();
headers.set("X-Job-Id", "j-42");
ResponseEntity<String> second = new ResponseEntity<>(
        "queued", headers, HttpStatus.ACCEPTED);

// 3. Tạo nhanh kết quả 200.
ResponseEntity<String> third = ResponseEntity.ok("queued");
```

Đây là những **statement minh họa** đặt trong method Java, không phải chương trình Java độc lập. Các kiểu cần import `org.springframework.http.ResponseEntity`, `HttpHeaders`, `HttpStatus`. `first` và `second` đều có status 202/header `X-Job-Id`/body `queued`; `third` trả 200 và không thêm header đó.

Các phương thức builder nổi bật:

| Cách viết | HTTP status mặc định hoặc mục tiêu | Trả body? |
| --- | --- | --- |
| `ResponseEntity.ok(body)` | `200 OK` | Có |
| `ResponseEntity.ok().header(...).body(body)` | `200 OK` | Có |
| `ResponseEntity.status(HttpStatus.ACCEPTED).body(body)` | `202 Accepted` | Có |
| `ResponseEntity.created(uri).body(body)` | `201 Created` và `Location` | Có |
| `ResponseEntity.noContent().build()` | `204 No Content` | Không |
| `ResponseEntity.badRequest().body(error)` | `400 Bad Request` | Có |
| `ResponseEntity.notFound().build()` | `404 Not Found` | Không |
| `ResponseEntity.status(HttpStatus.CONFLICT).body(error)` | `409 Conflict` | Có |
| `ResponseEntity.status(HttpStatus.SEE_OTHER).location(uri).build()` | `303 See Other` và `Location` | Không trong ví dụ |
| `ResponseEntity.of(optional)` | `200` nếu có giá trị, `404` nếu rỗng | Theo Optional |

Các method trên thể hiện **những kiểu response khác nhau**. Không chọn status theo sở thích: mã phải khớp kết quả thao tác và hợp đồng API.

### 2.1. `ResponseEntity<T>` là kiểu dữ liệu có generic

```java
ResponseEntity<BookDto> bookResponse;
ResponseEntity<List<BookDto>> booksResponse;
ResponseEntity<String> textResponse;
ResponseEntity<Void> noBodyResponse;
ResponseEntity<byte[]> binaryResponse;
```

Generic `T` mô tả kiểu body ở compile time. Nó giúp IDE, người viết code và test hiểu hợp đồng trả về. `ResponseEntity<Void>` đặc biệt hữu ích cho endpoint trả status/header nhưng không có body, như `204 No Content`. Nếu một method cần trả `BookDto` hoặc `ApiError` tùy nhánh, có thể trả `ResponseEntity<?>` hoặc thiết kế exception handler/error abstraction nhất quán; đừng ép tất cả response thành chuỗi thô.

## 3. Status code và hành vi REST đúng ngữ nghĩa

| Mã | Ngữ nghĩa điển hình | Ví dụ |
| --- | --- | --- |
| `200 OK` | Đọc hoặc cập nhật thành công và có representation trả về | GET sách, PUT trả object |
| `201 Created` | Tạo được tài nguyên mới | POST tạo sách kèm `Location` |
| `202 Accepted` | Đã tiếp nhận, xử lý chưa chắc hoàn tất | Đưa job vào hàng đợi |
| `204 No Content` | Thành công và không gửi body | DELETE thành công |
| `301/302/303/307/308` | Điều hướng sang URI khác, mỗi mã có quy tắc method khác nhau | `303 See Other` sau POST |
| `304 Not Modified` | Điều kiện cache cho biết không cần gửi representation | Conditional GET/HEAD |
| `400 Bad Request` | Request không hợp lệ về cú pháp/đầu vào | JSON sai định dạng |
| `401 Unauthorized` | Chưa có xác thực hợp lệ; thường kèm challenge khi áp dụng | Authentication bắt buộc |
| `403 Forbidden` | Danh tính không được phép thao tác | Thiếu quyền |
| `404 Not Found` | Không có tài nguyên tương ứng hoặc không tiết lộ sự tồn tại | GET ID không có |
| `409 Conflict` | Xung đột trạng thái tài nguyên | Trùng mã duy nhất |
| `412 Precondition Failed` | HTTP precondition thất bại | `If-Match`/ETag không khớp |
| `422 Unprocessable Content` | Body có cấu trúc hợp lệ nhưng nội dung không thể xử lý theo policy | Validation nghiệp vụ nếu API chọn 422 |
| `500 Internal Server Error` | Lỗi server không được xử lý thành phản hồi cụ thể | Không cố trả 200 cho lỗi hệ thống |

Lưu ý `202` **không đồng nghĩa tác vụ đã thành công**; với xử lý bất đồng bộ, trả job ID và cung cấp API theo dõi trạng thái khi phù hợp. `204`/`304` không có response body theo semantics HTTP: dùng `build()`, không cố thêm JSON body. Với lỗi đầu vào, thống nhất quy ước trả 400 hay 422 và cách biểu diễn lỗi; Spring có các default error handling riêng có thể khác thiết kế cụ thể của API.

## 4. Builder API: ba thành phần được thiết lập ra sao?

### 4.1. Status có sẵn hoặc status bất kỳ

```java
ResponseEntity<String> ok = ResponseEntity.ok("done");
ResponseEntity<String> accepted = ResponseEntity
        .status(HttpStatus.ACCEPTED)
        .body("processing");
ResponseEntity<String> limited = ResponseEntity
        .status(429)
        .header("Retry-After", "30")
        .body("try later");
```

`ResponseEntity.status(...)` nhận mã trạng thái hợp lệ; các constant `HttpStatus` giúp biểu đạt ý định. Trong Spring Framework 6+, `HttpStatusCode` là abstraction cho status; các overload/builder tương thích khác nhau theo version. Chọn `HttpStatus` hoặc integer để code minh họa đơn giản.

### 4.2. Header tự định nghĩa

```java
return ResponseEntity.ok()
        .header("X-Trace-Id", traceId)
        .header("X-API-Version", "1")
        .body(dto);
```

Các header phải được tạo từ dữ liệu đáng tin cậy hoặc đã kiểm tra; không phản chiếu tùy ý chuỗi client gửi vào header. Header `X-Trace-Id` là ví dụ metadata, không mang vai trò xác thực. Nếu JavaScript chạy từ origin khác cần đọc custom response header, ngoài header đó còn phải cấu hình CORS `Access-Control-Expose-Headers` tương ứng (khi policy cho phép).

### 4.3. Dùng builder tiện lợi cho header chuẩn

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .cacheControl(CacheControl.noStore())
        .header("X-Source", "catalog")
        .body(bookDto);
```

- `contentType(MediaType.APPLICATION_JSON)` đặt `Content-Type: application/json`.
- `cacheControl(CacheControl.noStore())` hướng dẫn cache không lưu representation này.
- `header("X-Source", "catalog")` thêm header tùy biến.
- `body(bookDto)` kết thúc builder và tạo `ResponseEntity<BookDto>`.

Các builder tiện lợi khác gồm `location(URI)`, `contentLength(long)`, `allow(HttpMethod...)`, `eTag(String)`, `lastModified(...)` và `headers(HttpHeaders)` theo nhu cầu. Đừng khai báo `Content-Length` đoán mò cho JSON do converter tạo vì serialization có thể biến đổi byte so với độ dài ký tự; để server quyết định khi phù hợp.

### 4.4. HTTP body vẫn cần converter

`ResponseEntity<String>` thường dùng `StringHttpMessageConverter`; `ResponseEntity<BookDto>` thường dùng Jackson JSON converter khi media type là JSON; `ResponseEntity<byte[]>` dùng converter byte array; `ResponseEntity<Resource>` dùng resource converter phù hợp. Việc viết:

```java
ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body("not valid JSON");
```

không biến chuỗi `not valid JSON` thành JSON hợp lệ. Media type là **cam kết định dạng**, không phải lệnh tự động serialize lại String. Trả object DTO thay vì tự nối chuỗi JSON để converter serialize đúng.

## 5. Tạo mới tài nguyên: `201 Created` và `Location`

Một POST tạo sách thường có quá trình:

1. Nhận request DTO chứa field mà client được phép gửi.
2. Kiểm tra input và quyền tạo.
3. Tạo ID mới và lưu thành công.
4. Trả `201 Created`; header `Location` trỏ đến URI của sách; body có thể là representation vừa tạo.

Ví dụ method:

```java
@PostMapping("/books")
public ResponseEntity<BookDto> create(@RequestBody CreateBookRequest input) {
    BookDto saved = service.create(input); // Service do ứng dụng cung cấp
    URI uri = URI.create("/books/" + saved.id());

    return ResponseEntity.created(uri).body(saved);
}
```

Đây là method **minh họa**, phụ thuộc `BookDto`, `CreateBookRequest` và `service` chưa khai báo; xem chương trình độc lập ở mục 10 để chạy ngay. Trong ví dụ này `Location` là relative reference hợp lệ. Nếu cần absolute URL hoặc ứng dụng có context path/proxy, tạo URI theo cấu hình đáng tin cậy và chính sách external base URL thay vì tự tin tưởng header forward từ client.

Không trả 201 khi chưa tạo xong tài nguyên, ví dụ job chỉ mới xếp hàng: cân nhắc `202 Accepted` và URI theo dõi. Đừng đồng nhất `Location` với đường dẫn file nội bộ trên server.

## 6. GET: 200 có body, 404 khi không có

Đối với GET có thể trả object khi có và 404 khi vắng:

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> get(@PathVariable long id) {
    return service.findById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
}
```

Đây cũng là **method minh họa**. Hàm `service.findById(id)` giả định trả `Optional<BookDto>`. Một lựa chọn ngắn:

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> get(@PathVariable long id) {
    return ResponseEntity.of(service.findById(id));
}
```

`ResponseEntity.of(Optional<T>)` trả status 200 với body khi Optional có giá trị, ngược lại 404 không body. Phương án này đơn giản nhưng không trả error DTO tùy biến cho 404. Trong API thực tế, chọn một chiến lược error nhất quán (exception handler, `ProblemDetail`, hoặc body error riêng) thay vì viết mỗi endpoint một dạng ngẫu nhiên.

### 6.1. Khi nào 404 có body?

```java
if (book == null) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("Book not found"));
}
```

Trả body JSON mô tả lỗi là hợp lệ, miễn status vẫn là 404. Khi method có hai body type khác nhau, khai báo `ResponseEntity<?>` hoặc dùng mô hình error response thống nhất. Không bao giờ trả `200 OK` với `{"error":"not found"}` cho một tình huống đáng lẽ là 404 chỉ để “đỡ lỗi” phía client.

## 7. PUT, PATCH, DELETE: chọn 200, 204, 404 theo kết quả

Với thao tác cập nhật:

```java
@PutMapping("/books/{id}")
public ResponseEntity<BookDto> replace(
        @PathVariable long id,
        @RequestBody UpdateBookRequest input) {
    Optional<BookDto> updated = service.replace(id, input);
    return updated.map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
}
```

Đây là ví dụ service không độc lập. Trả `200` nếu muốn gửi representation sau cập nhật; `204` nếu cập nhật thành công nhưng không cần body; `404` nếu bản ghi không tồn tại và API chọn không tự tạo mới với PUT.

DELETE:

```java
@DeleteMapping("/books/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    boolean existed = service.deleteIfExists(id);
    return existed
            ? ResponseEntity.noContent().build()
            : ResponseEntity.notFound().build();
}
```

API có thể lựa chọn semantics idempotent cho DELETE theo policy: gọi xóa lặp lại không tạo hiệu ứng ngoài ý muốn, nhưng status cho lần gọi sau **có thể là 204 hoặc 404** tùy hợp đồng. Đừng coi hai status ấy tương đương về ý nghĩa; công bố rõ cho client.

**Đúng với `204`:** body phải rỗng. Không viết `ResponseEntity.noContent().build()` rồi cố thêm JSON thông điệp thành công. Nếu cần body, dùng status thích hợp như 200.

## 8. Thông tin lỗi có cấu trúc: `ProblemDetail` và status

Spring Framework 6 có `org.springframework.http.ProblemDetail` phục vụ phản hồi lỗi theo Problem Details (hiện nay RFC 9457):

```java
@GetMapping("/inventory/{id}")
public ResponseEntity<ProblemDetail> inventory(@PathVariable long id) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy sản phẩm " + id);
    problem.setTitle("Product not found");
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(problem);
}
```

Đây là **method minh họa** trong controller, không chạy cùng demo nếu chưa chép vào lớp phù hợp. Với hệ sinh thái Spring MVC hỗ trợ ProblemDetail, response có thể được render dưới `application/problem+json`. Đảm bảo status HTTP và `problem.status` nhất quán; không đặt status body 404 rồi trả HTTP 200. Đừng đưa stacktrace, SQL, khóa API hoặc chi tiết nội bộ vào error body cho client.

Nếu Spring MVC và ứng dụng đã có `@RestControllerAdvice` / `@ExceptionHandler` thống nhất lỗi, không cần mọi method xây error body thủ công. Với validation, Spring có thể ném exception trước khi controller method chạy; xử lý ở advice phù hợp, tránh nghĩ rằng mọi lỗi sẽ đi qua nhánh `if` của method.

## 9. Headers quan trọng trong REST response

### 9.1. `Content-Type` và `Accept`

Request header `Accept: application/json` cho biết client muốn nhận JSON. `@GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)` hạn chế representation route cho phép. Nếu client chỉ chấp nhận XML nhưng server không có XML representation, thường trả **406 Not Acceptable**.

Response header `Content-Type: application/json` cho biết **body thực tế** có định dạng JSON. Dùng đúng DTO/converter thay vì đổi header để “đánh lừa” client. Request `Content-Type` lại mô tả **body gửi lên**, ví dụ POST `application/json`; nếu route `consumes` không khớp, có thể trả **415 Unsupported Media Type**.

### 9.2. `Location`

`Location` phổ biến với `201 Created` hoặc response redirect. Với `201` nó biểu thị URI liên quan đến tài nguyên mới; với `303 See Other` nó hướng dẫn client chuyển tới tài nguyên khác theo semantics HTTP. Hãy tạo URI bằng dữ liệu đã chuẩn hóa và chính sách host tin cậy để tránh open redirect hoặc host-header injection.

### 9.3. `Cache-Control`, `ETag`, `Last-Modified`

Một GET của tài nguyên có thể trả:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(60, TimeUnit.SECONDS).cachePrivate())
        .eTag("\"book-v7\"")
        .body(book);
```

Đây là **đoạn code minh họa**: cần `java.util.concurrent.TimeUnit`, `org.springframework.http.CacheControl`; `book` phải được khai báo. `ETag` là validator cho **phiên bản representation cụ thể**, không nên đặt một tag cố định nếu nội dung có thể thay đổi. Builder `eTag(...)` chấp nhận giá trị hợp lệ có dấu nháy hoặc tự xử lý dấu nháy theo quy tắc của phiên bản Spring.

Khi client gửi conditional request `If-None-Match` hoặc `If-Modified-Since`, Spring MVC có thể đánh giá validator và trả **304 Not Modified** (không body) nếu các điều kiện phù hợp, tùy cách request được xử lý. `ETag` giúp tối ưu tải mạng; `Cache-Control` xác định chính sách lưu cache. `Cache-Control: no-store` phù hợp với phản hồi nhạy cảm cần tránh lưu trữ; `private` không đồng nghĩa với bảo mật dữ liệu tuyệt đối.

Với cập nhật có điều kiện, `If-Match` và `412 Precondition Failed` có thể ngăn lost update, nhưng **chỉ đặt ETag trên GET không tự bảo đảm concurrency**. Cần xử lý precondition/phiên bản khi PUT/PATCH/DELETE, kiểm thử các trường hợp xung đột. Spring có hỗ trợ HTTP conditional request ở tầng MVC; persistence vẫn cần cơ chế concurrency của chính nó.

### 9.4. `Content-Disposition` cho file

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"example.txt\"")
        .body(resource);
```

Đây là snippet dùng `org.springframework.core.io.Resource` và `HttpHeaders`; Spring chọn resource converter phù hợp. Không dùng tên file do client nhập trực tiếp trong header nếu chưa xử lý an toàn. Không nạp toàn bộ file lớn vào byte array nếu có thể dùng Resource/streaming phù hợp và kiểm soát quyền tải file.

## 10. Ví dụ hoàn chỉnh: REST Book API chạy với Java 17+ và Spring Boot 3.x

Ví dụ sử dụng **bộ nhớ trong ứng dụng** để quan sát chính xác status/header/body mà không phụ thuộc database hay security. Sau khi restart, dữ liệu đặt lại. Tạo Spring Boot 3.x project trên [Spring Initializr](https://start.spring.io/) với Java 17+ và dependency **Spring Web**. Dùng Maven wrapper do Initializr sinh.

Đặt toàn bộ mã dưới đây vào `src/main/java/com/example/demo/DemoApplication.java`. File có một public class và các top-level package-private types, hợp lệ trên Java 17:

```java
package com.example.demo;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record Book(long id, String title, String author) {
}

record BookInput(String title, String author) {
}

record ApiError(String message) {
}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final Map<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(11);

    BookController() {
        books.put(10L, new Book(10, "Java Basics", "Minh"));
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> get(@PathVariable("id") long id) {
        Book book = books.get(id);
        if (book == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiError("Book " + id + " not found"));
        }

        return ResponseEntity.ok()
                .header("X-Book-Id", Long.toString(id))
                .cacheControl(CacheControl.noStore())
                .body(book);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> create(@RequestBody BookInput input) {
        long id = nextId.getAndIncrement();
        Book saved = new Book(id, input.title(), input.author());
        books.put(id, saved);

        URI location = URI.create("/api/books/" + id);
        return ResponseEntity.created(location)
                .header("X-Resource-Type", "book")
                .body(saved);
    }

    @PutMapping(path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> replace(
            @PathVariable("id") long id,
            @RequestBody BookInput input) {

        if (!books.containsKey(id)) {
            return ResponseEntity.notFound().build();
        }

        Book saved = new Book(id, input.title(), input.author());
        books.put(id, saved);
        return ResponseEntity.ok(saved);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable("id") long id) {
        if (books.remove(id) == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.noContent().build();
    }

    @GetMapping(path = "/text",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> text() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/plain;charset=UTF-8"))
                .body("Book API ready");
    }

    @GetMapping(path = "/download",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Resource> download() {
        Resource file = new ByteArrayResource(
                "BOOK\n".getBytes(StandardCharsets.UTF_8));

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"book.txt\"")
                .body(file);
    }

    @GetMapping("/redirect")
    public ResponseEntity<Void> redirect() {
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create("/api/books/10"))
                .build();
    }
}
```

**Giải thích thiết kế:**

- `get` trả 200/JSON + `X-Book-Id` và `Cache-Control: no-store` khi tìm thấy; trả 404 + `ApiError` nếu không có.
- `create` cấp ID mới, lưu vào map, trả 201 + `Location` + `X-Resource-Type` + JSON body. `URI.create("/api/books/" + id)` dùng **relative URI** thích hợp cho demo tại context path rỗng; ứng dụng có prefix/proxy cần xây URI tương ứng.
- `replace` chỉ cập nhật ID đã tồn tại, trả 200 + representation mới hoặc 404 không body.
- `delete` trả 204 không body khi vừa xóa; gọi lại nhận 404 theo policy của demo.
- `text` chứng minh `ResponseEntity<String>` có thể trả text/plain; `download` dùng `ResponseEntity<Resource>` để gửi file; `redirect` trả 303 + Location.
- `ConcurrentHashMap` và `AtomicLong` phục vụ **demo một tiến trình**; không phải persistence, transaction, authorization hay giải pháp đồng bộ cập nhật production.
- Demo không có validation đầu vào; code thực tế cần request DTO kèm ràng buộc, Bean Validation, kiểm tra quyền và xử lý domain exception.

### 10.1. Chạy chương trình

Từ thư mục gốc dự án Maven do Spring Initializr tạo:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

Khi ứng dụng khởi động, server mặc định nghe `http://localhost:8080` (nếu chưa đổi `server.port` hoặc context path). Chạy mỗi nhóm request theo thứ tự và trên trạng thái mới khởi động để so sánh kết quả chính xác.

### 10.2. GET thành công: 200 + JSON + headers

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/books/10
```

Phần quan trọng của response:

```http
HTTP/1.1 200
Content-Type: application/json
X-Book-Id: 10
Cache-Control: no-store

{"id":10,"title":"Java Basics","author":"Minh"}
```

Thứ tự header, dấu cách và các header do container thêm có thể khác; body JSON dự kiến có ba field theo cấu trúc record. `-i` hiển thị status và headers; `Content-Length` có thể do server quyết định.

### 10.3. GET không tồn tại: 404 + JSON lỗi

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/books/999
```

Status **404 Not Found**; body từ `ApiError`:

```json
{"message":"Book 999 not found"}
```

Nếu client gửi `Accept` không tương thích với `produces=application/json`, Spring có thể chọn xử lý 406 trước khi gọi controller; đừng coi kết quả 404 là bắt buộc cho mọi header.

### 10.4. POST tạo mới: 201 + Location + JSON

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"title":"Clean Code","author":"Robert Martin"}'
```

Trên lần đầu POST sau khi khởi động, server cấp ID `11` và trả:

```http
HTTP/1.1 201
Location: /api/books/11
X-Resource-Type: book
Content-Type: application/json

{"id":11,"title":"Clean Code","author":"Robert Martin"}
```

Các field/header có thể được format/thứ tự khác tùy runtime; status, Location, custom header và nội dung JSON là điều cần kiểm chứng. Tiếp đó `GET /api/books/11` có thể trả object vừa tạo. Nếu POST thêm lần nữa, ID sẽ tăng; đừng giả định ID luôn là `11`.

### 10.5. PUT thay thế: 200 hoặc 404

```bash
curl -i -X PUT http://localhost:8080/api/books/10 \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"Spring MVC","author":"Lan"}'
```

Status **200 OK**, body:

```json
{"id":10,"title":"Spring MVC","author":"Lan"}
```

Nếu PUT tới ID `999` (chưa được tạo), demo trả **404 không body**. Đây là policy của endpoint: nhiều API có thể chọn PUT tạo tài nguyên tại URI đích nếu hợp đồng cho phép; lúc đó logic và status cần thiết kế khác.

### 10.6. DELETE: 204 hoàn toàn không có body

```bash
curl -i -X DELETE http://localhost:8080/api/books/10
```

Lần xóa đầu sau khi book `10` còn tồn tại: status **204 No Content**, không body. Lần xóa thứ hai: **404 Not Found**, không body theo code demo. Nếu chạy lại GET `/api/books/10` sau DELETE thì nhận 404 với `ApiError`.

### 10.7. Text, file và redirect

Text:

```bash
curl -i http://localhost:8080/api/books/text
```

Status 200; header `Content-Type: text/plain;charset=UTF-8`, body:

```text
Book API ready
```

File:

```bash
curl -i http://localhost:8080/api/books/download
```

Status 200; `Content-Type: application/octet-stream`, `Content-Disposition: attachment; filename="book.txt"`, body chính xác **5 byte** gồm `BOOK` và newline. Lưu bằng `curl -o book.txt http://localhost:8080/api/books/download` để kiểm tra file riêng, thay vì dùng `-i` khi muốn nội dung binary sạch.

Redirect:

```bash
curl -i http://localhost:8080/api/books/redirect
```

Status **303 See Other**, header `Location: /api/books/10`, không body. Không dùng `curl -L` khi muốn quan sát response redirect ban đầu vì `-L` làm cURL đi tiếp sang URI được chỉ định.

Với Windows PowerShell, dùng `curl.exe` và viết mỗi lệnh trên một dòng (dấu `\` nối dòng ở Bash không có tác dụng tương đương trong PowerShell).

## 11. So sánh `ResponseEntity` với các cách trả response khác

| Cách trả về | Điều khiển status | Điều khiển headers | Body | Thích hợp |
| --- | --- | --- | --- | --- |
| DTO trực tiếp từ `@RestController` | Thường 200 mặc định | Thường phụ thuộc lớp khác | Có | GET đơn giản |
| `@ResponseStatus(HttpStatus.CREATED)` | Status thường **cố định** theo annotation | Không trực tiếp qua annotation này | Có thể có | Method luôn một status |
| `ResponseEntity<T>` | Linh hoạt theo kết quả từng nhánh | Có | Có/không | REST endpoints |
| `HttpEntity<T>` | Không tự khai báo status riêng | Có | Có | Response chỉ cần headers/body |
| `HttpServletResponse` | Có, thao tác thấp cấp | Có | Tự ghi hoặc framework xử lý theo pattern | Servlet streaming/integration |
| Ném exception + `@ExceptionHandler` | Qua handler lỗi | Có thể cấu hình | Có thể có | Chuẩn hóa lỗi toàn API |

Ví dụ annotation:

```java
@ResponseStatus(HttpStatus.CREATED)
@PostMapping("/simple")
public BookDto create(@RequestBody BookInput input) {
    return service.create(input);
}
```

Đây là code **minh họa**, yêu cầu `service` do ứng dụng định nghĩa. `@ResponseStatus` tiện khi toàn method luôn cùng status, nhưng khi cùng handler có thể trả 201, 400, 409 tùy trạng thái, `ResponseEntity` hoặc exception mapping thể hiện linh hoạt hơn.

**Lưu ý:** `ResponseEntity` có thể trả từ `@Controller` thông thường, không bắt buộc class gắn `@RestController`. Spring nhận diện kiểu return và viết HTTP response tương ứng, không coi nó là model/view name.

## 12. Test thật status + header + body bằng MockMvc

Trong ứng dụng Spring MVC, `MockMvc` giúp test kết quả HTTP mà không cần khởi chạy server mạng thật. Spring Boot test thường cần dependency `spring-boot-starter-test`. Ví dụ kiểm thử endpoint GET trên ứng dụng ở mục 10:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getBookReturnsStatusHeaderAndBody() throws Exception {
        mvc.perform(get("/api/books/10")
                        .accept("application/json"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Book-Id", "10"))
                .andExpect(jsonPath("$.id").value(10))
                .andExpect(jsonPath("$.title").value("Java Basics"));
    }

    @Test
    void missingBookReturns404() throws Exception {
        mvc.perform(get("/api/books/999")
                        .accept("application/json"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message")
                        .value("Book 999 not found"));
    }
}
```

Lưu ở `src/test/java/com/example/demo/BookControllerTest.java`. Đây là **file test riêng** theo JUnit 5; không đặt cùng `DemoApplication.java`. Chạy:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Hai test đọc trạng thái mới từ controller trong Spring test context, không gọi DELETE; không phụ thuộc thao tác cURL thực hiện ở một process khác. Nếu cấu hình security được thêm sau này, test phải xử lý security filter/token/role tương ứng.

Khi test endpoint tạo/xóa, nên xác nhận các nhánh `201` + `Location`, `204` + body rỗng, `404` và `406/415` khi sử dụng consumes/produces. Test header + body cùng nhau giúp ngăn trường hợp trả đúng JSON nhưng status sai.

## 13. Lỗi thường gặp khi dùng ResponseEntity

| Lỗi | Vấn đề | Cách sửa |
| --- | --- | --- |
| Trả `ResponseEntity.ok(errorDto)` khi lỗi | Client thấy 200 dù thao tác thất bại | Chọn status 4xx/5xx thích hợp |
| POST tạo xong nhưng luôn trả 200 | Mất tín hiệu Created cho client | `ResponseEntity.created(location).body(saved)` |
| Trả `204` kèm JSON | Vi phạm ý nghĩa no-content | Dùng `build()` hoặc chọn 200 nếu có body |
| Tự nối chuỗi JSON | Sai escaping/schema, khó kiểm thử | Trả DTO qua converter |
| Đặt `Content-Type: application/json` cho String không hợp lệ | Client parse lỗi | Dùng object JSON hoặc định dạng đúng |
| Tự điền `Content-Length` theo `String.length()` | Số ký tự không bằng số byte UTF-8 | Để framework tính khi phù hợp |
| Header `Location` dùng host từ input không tin cậy | Rủi ro open redirect/host injection | Tạo URI bằng base URL/forwarded-header policy tin cậy |
| Response cache nhầm nội dung riêng tư | Có thể lưu/được chia sẻ ngoài ý muốn | `CacheControl.noStore()` hoặc private policy thích hợp |
| Gán ETag cố định cho dữ liệu biến đổi | Client nhận 304 cũ hoặc state sai | Tính validator theo phiên bản/representation |
| Dùng `ResponseEntity<?>` khắp code vô cớ | Hợp đồng body khó đọc | Ưu tiên `ResponseEntity<Dto>` và error handler |
| Trả 404 cho mọi exception | Che giấu bug và làm client hiểu sai | Phân loại lỗi nghiệp vụ, validation, hệ thống |
| Lẫn response thủ công với converter | Ghi body hai lần, header đã commit | Chọn rõ response strategy cho method |

## 14. Những điểm cần nhớ khi triển khai production

- **Tách request DTO và response DTO:** `ResponseEntity` không lọc field nhạy cảm. Không trả trực tiếp entity chứa password hash, tenant secrets, internal notes chỉ vì serializer tiện.
- **Kiểm tra quyền trước khi tạo body:** status 403/404 tùy chính sách không được quyết định chỉ từ dữ liệu client gửi. Ownership và authorization vẫn cần ở service/security layer.
- **HTTP header là một phần hợp đồng API:** các header `Location`, `ETag`, `Retry-After`, `Cache-Control` và `Content-Disposition` cần đúng mục đích. Custom header có thể bị proxy/caching/CORS policy ảnh hưởng.
- **Chú ý phương thức HEAD và conditional GET:** không mặc định HEAD phải có body; `304` cũng không mang representation body.
- **Đừng ép response đã được commit:** ghi trực tiếp vào `HttpServletResponse` rồi đổi status/header sau flush có thể không có tác dụng; với `ResponseEntity` nên để Spring chịu trách nhiệm serialize body.
- **Tránh response quá lớn:** `ResponseEntity<byte[]>` giữ dữ liệu trong RAM; dùng `Resource`/streaming hoặc phân trang khi phù hợp.
- **Đồng bộ status và payload lỗi:** nếu body theo RFC 9457 chứa `status`, trường này cần phù hợp HTTP status; không lộ stacktrace hay dữ liệu nhạy cảm.

### Checklist chọn kết quả cho handler

1. Request hợp lệ và được phép xử lý chưa? Nếu chưa, chọn status 4xx đúng nguyên nhân và error contract.
2. Tài nguyên có tồn tại/được tạo xong không? GET có thể 200/404; POST đã tạo có thể 201/Location; job chưa hoàn tất có thể 202.
3. Có body có ích không? Nếu không, chọn response không body như 204 khi ngữ nghĩa phù hợp.
4. Client yêu cầu media type nào qua `Accept`? `produces` và converter có hỗ trợ không?
5. Có cần header chuẩn như `Location`, `Cache-Control`, `ETag`, `Content-Disposition`?
6. Test đã kiểm tra **status + header + body (hoặc body rỗng)** và những nhánh lỗi chưa?

## 15. Tự kiểm tra

**Câu 1.** Trong `@RestController`, cần trả 201, header `Location: /api/orders/5`, JSON object `OrderDto`. Viết thế nào?

```java
return ResponseEntity
        .created(URI.create("/api/orders/5"))
        .body(orderDto);
```

Đoạn trên yêu cầu `orderDto` được tạo/lưu thành công. `created` tự đặt status 201 và Location; DTO đi qua converter.

**Câu 2.** Khi DELETE thành công nhưng không trả nội dung, nên dùng `ResponseEntity.ok("deleted")` hay `ResponseEntity.noContent().build()`?

**Đáp án:** Dùng `noContent().build()` nếu API muốn thể hiện thành công không body, tức 204. Có thể chọn 200 kèm representation theo hợp đồng khác, nhưng không được đính body vào 204.

**Câu 3.** Tại sao `ResponseEntity.status(404).body(error)` khác `ResponseEntity.ok(error)`?

**Đáp án:** Body có thể giống nhau nhưng HTTP status quyết định cách client, cache, proxy, monitoring hiểu kết quả. Trả 200 cho lỗi 404 là sai ngữ nghĩa.

**Câu 4.** `ResponseEntity<String>` và `ResponseEntity<MyDto>` có nhất thiết sử dụng cùng converter không?

**Đáp án:** Không. Converter phụ thuộc kiểu Java và media type; chuỗi thường dùng string converter, DTO JSON thường dùng Jackson converter.

**Câu 5.** Nếu POST trả 201 nhưng resource chưa được tạo mà chỉ mới vào hàng đợi, mã nào đáng cân nhắc hơn?

**Đáp án:** `202 Accepted` kèm metadata/job tracking phù hợp, vì xử lý chưa hoàn tất.

**Câu 6.** Chỉ cần gắn `eTag("v1")` lên GET là PUT tự chống ghi đè phiên bản cũ phải không?

**Đáp án:** Không. Phải có xử lý HTTP precondition như `If-Match`/`412` hoặc concurrency control ở service/database; ETag GET đơn lẻ không khóa cập nhật.

## 16. Tài liệu chính thức

- [Spring Framework — `ResponseEntity`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): cú pháp builder, status/header/body, Resource và async.
- [Spring Framework — Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): `ResponseEntity`, `HttpEntity`, `@ResponseBody` và các return type khác.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): `Cache-Control`, `ETag` và conditional HTTP.
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): cách converter serialize body theo kiểu Java/media type.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail` và error handling trong REST.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `consumes`, `produces` và content negotiation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): định nghĩa các status/header HTTP chuẩn.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): khuôn dạng body lỗi có cấu trúc.

**Ghi nhớ cốt lõi:** trong Spring MVC, `ResponseEntity<T>` là cách khai báo rõ **status + headers + body** cho từng nhánh REST response. Chọn status theo kết quả thực tế, dùng builder cho header tiêu chuẩn, để converter ghi đúng biểu diễn của `T`, và kiểm chứng đủ cả ba phần bằng HTTP/MockMvc test.
