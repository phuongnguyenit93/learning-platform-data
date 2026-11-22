# Tạo tài nguyên với HTTP 201 Created và header Location trong Spring MVC

## 1. Tình huống: một yêu cầu POST tạo ra tài nguyên mới

Giả sử một ứng dụng REST quản lý sách. Client gửi:

```http
POST /api/books HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC thực hành"}
```

Server kiểm tra dữ liệu, tạo bản ghi với ID do server cấp (ví dụ `1001`) và phản hồi:

```http
HTTP/1.1 201 Created
Location: /api/books/1001
Content-Type: application/json

{"id":1001,"title":"Spring MVC thực hành"}
```

Phản hồi này truyền đạt **ba điều độc lập nhưng bổ trợ nhau**:

1. **`201 Created`**: HTTP request đã hoàn tất và dẫn đến một hay nhiều tài nguyên mới được tạo.
2. **`Location: /api/books/1001`**: URI của **tài nguyên chính** được tạo bởi request; client có thể dùng URI này trong một request mới nếu server hỗ trợ truy xuất ở URI đó.
3. **JSON response body**: biểu diễn hoặc thông tin tóm tắt tài nguyên mới, chẳng hạn ID và tiêu đề. Body **có thể có hoặc không**; `201` không bắt buộc JSON body.

Một client có thể tiếp tục:

```http
GET /api/books/1001 HTTP/1.1
Host: api.example.com
Accept: application/json
```

Nếu API hỗ trợ GET tài nguyên đó và tài nguyên vẫn tồn tại, phản hồi thường là `200 OK` với biểu diễn tương ứng. **Đừng suy ra rằng mọi `Location` luôn là URL GET được phép truy cập**: quyền, trạng thái hoặc contract riêng có thể giới hạn; API cần công bố rõ điều này.

Mục tiêu bài: hiểu ngữ nghĩa HTTP chuẩn, chọn response Spring MVC thích hợp, tạo URI đúng, bảo vệ hợp đồng REST và viết kiểm thử xác nhận HTTP status/header/body.

## 2. Ngữ nghĩa chính xác theo RFC 9110

RFC 9110, mục **15.3.2 — 201 Created**, mô tả trạng thái này khi request đã thành công và tạo **một hoặc nhiều tài nguyên**. Tài nguyên chính được xác định bởi header `Location` nếu hiện diện; nếu không, tài nguyên chính được xác định bởi **target URI** của request.

Điều đó kéo theo các nguyên tắc:

- `201` là phản hồi **thành công** (nhóm 2xx), **không phải chuyển hướng** (nhóm 3xx). HTTP client **không tự động GET `Location` chỉ vì status là 201**.
- `Location` nên trỏ tới tài nguyên chính được tạo, ví dụ `/api/books/1001`, không phải luôn trỏ về collection nhận POST `/api/books`.
- `Location` có thể chứa **URI tuyệt đối** (`https://api.example.com/api/books/1001`) hoặc **relative URI reference** (`/api/books/1001`). RFC 9110 cho phép URI-reference; client resolve relative Location so với URI request.
- `201` **không đòi hỏi** có body; body nếu có thường mô tả kết quả hành động hoặc tài nguyên mới. Khi muốn gửi JSON, phải đảm bảo serialization và `Content-Type` tương ứng.
- Server nên tạo URI có ý nghĩa bền vững, không làm client phải suy diễn vị trí từ một ID trả riêng trong body.
- Nếu POST tạo nhiều tài nguyên, `Location` chỉ đại diện **primary resource**; body có thể liệt kê những tài nguyên khác theo hợp đồng đã công bố.
- Header `Location` không phải cam kết rằng mọi thao tác với tài nguyên đều được cấp quyền hoặc rằng tài nguyên luôn tồn tại mãi mãi.

**Ví dụ phản hồi 201 không có body hợp lệ:**

```http
HTTP/1.1 201 Created
Location: /api/books/1001
Content-Length: 0
```

Tuy nhiên, với `POST /api/books`, **nên trả `Location`** vì client cần biết URI tài nguyên mới. Nếu bỏ Location, fallback của chuẩn sang target URI `/api/books` thường không phản ánh mục tiêu định danh bản ghi con theo thiết kế REST thông dụng. Đây là lý do header này có giá trị dù status 201 về mặt cú pháp không bắt buộc luôn có Location.

### `Location` khác `Content-Location`

| Header | Trả lời câu hỏi | Trong một 201 thông dụng |
| --- | --- | --- |
| `Location` | “URI tài nguyên chính được tạo ở đâu?” | `/api/books/1001` |
| `Content-Location` | “Biểu diễn trong **body hiện tại** tương ứng với URI nào?” | Có thể là `/api/books/1001` nếu body là biểu diễn hiện tại của tài nguyên |

Theo RFC 9110, với **201**, khi `Content-Location` trùng `Location`, thông điệp mang biểu diễn hiện tại của tài nguyên được tạo. Không cần tự thêm `Content-Location` cho mọi 201; chỉ dùng khi ý nghĩa representation và cache/content negotiation yêu cầu.

Đừng nhầm `Location` của **201** với `Location` của **301/302/303/307/308**: ở phản hồi 3xx, Location chỉ mục tiêu redirect; còn 201 không kích hoạt redirect.

## 3. Chọn đúng HTTP status cho thao tác tạo/sửa

| Hoạt động đã xảy ra | Mã phù hợp | Ý nghĩa |
| --- | --- | --- |
| POST tạo thành công tài nguyên mới | **201 Created** | Công việc tạo đã hoàn tất; thường kèm Location |
| POST thực hiện hành động nhưng không tạo tài nguyên mới | **200 OK** hoặc **204 No Content** | Theo hợp đồng và có body hay không |
| POST tiếp nhận yêu cầu, đang xử lý bất đồng bộ, chưa hoàn tất | **202 Accepted** | Đã nhận xử lý, chưa bảo đảm tạo thành công |
| PUT tại URI chưa tồn tại, tạo tài nguyên thành công | **201 Created** | Tạo tài nguyên tại target URI |
| PUT thay thế/sửa tài nguyên đã tồn tại | **200 OK** hoặc **204 No Content** | Tùy có trả nội dung |
| Tài nguyên không được tạo vì lỗi dữ liệu | **400 Bad Request** hoặc **422 Unprocessable Content** | Chọn theo cách API phân loại lỗi |
| Tạo xung đột với tài nguyên/trạng thái hiện có | **409 Conflict** | Ví dụ unique key trùng |
| Client thiếu xác thực hoặc không đủ quyền | **401 Unauthorized** / **403 Forbidden** | Không coi là tạo thành công |
| Tạo xong nhưng muốn điều hướng client GET tài nguyên khác | **303 See Other**, tùy use case | Đây là một lựa chọn redirect có chủ đích, khác với 201 |

**Đặc biệt với PUT:** RFC 9110 yêu cầu nếu PUT thành công và **trước đó không có biểu diễn hiện tại của target resource** thì server báo **201 Created**. Nếu target đã có và được cập nhật, thường dùng 200/204. Không đánh đồng mọi HTTP PUT với 200 hoặc mọi HTTP POST với 201.

**Với xử lý bất đồng bộ:** chỉ trả 201 khi việc tạo tài nguyên đã được xác nhận hoàn tất theo hợp đồng. Nếu request mới chỉ được xếp hàng và có thể thất bại sau đó, thông thường trả 202 cùng cơ chế kiểm tra trạng thái job. `Location` trong 202 (nếu có) có thể trỏ tới tài nguyên trạng thái xử lý; không ngầm hiểu nó đã là tài nguyên kết quả như trong 201.

## 4. Spring MVC có API nào để trả 201 + Location?

Cách thông dụng, rõ ràng là **`ResponseEntity.created(URI location)`** thuộc `org.springframework.http.ResponseEntity`:

```java
URI location = URI.create("/api/books/1001");

return ResponseEntity
        .created(location)
        .body(new BookResponse(1001L, "Spring MVC thực hành"));
```

Đây là **fragment trong method controller**. Khi gọi, builder tạo:

- `HttpStatus.CREATED` = 201.
- Header `Location` từ đối tượng `java.net.URI` đã truyền.
- Body được serialize bằng `HttpMessageConverter` thích hợp, ví dụ Jackson JSON.

Builder này tồn tại trong Spring Framework 5, 6 và 7; đây là API ổn định nên ưu tiên thay vì tự thêm status/header mỗi lần.

Các lựa chọn hợp lệ khác:

```java
// Chỉ trả status 201 + Location; không trả body:
return ResponseEntity.created(location).build();

// Tự chỉ định status và header:
return ResponseEntity.status(HttpStatus.CREATED)
        .location(location)
        .body(response);
```

Với method trả `ResponseEntity<BookResponse>`, hai đoạn trên là **phương án thay thế**, không đặt chung một method. Đoạn `build()` dùng khi API công bố 201 không có body.

**Chú ý `@ResponseStatus(HttpStatus.CREATED)`**:

```java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public BookResponse create(@RequestBody BookRequest body) {
    return service.create(body);
}
```

Annotation này đặt **status 201**, **không tự suy ra URI hoặc header `Location`**. Nếu cần Location, bạn phải set header bằng cách khác hoặc trả `ResponseEntity.created(uri)`. Cũng không dùng `ResponseEntity.ok(...)` sau khi tạo, trừ khi contract chủ động quy định 200.

## 5. Ví dụ Spring Boot 3.x + Java 17 hoàn chỉnh

Ví dụ API sau có **POST tạo sách** và **GET theo ID** để kiểm chứng rằng `Location` thực sự trỏ đến một tài nguyên mới. Lưu trữ bằng `ConcurrentHashMap` trong bộ nhớ cho mục đích học tập; một ứng dụng production cần repository/database và transaction đúng.

Baseline:

- Java 17 trở lên.
- Spring Boot 3.x, Spring Framework 6.x, Spring MVC Servlet.
- Spring Boot starters: `spring-boot-starter-web`, `spring-boot-starter-validation`, `spring-boot-starter-test`.
- Namespace `jakarta.validation.*` (Boot 3), Jackson được starter web cấu hình.

### 5.1. Dependencies

Trong dự án Gradle đã có Boot plugin, repository, Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn trên là **fragment `build.gradle`** chứ không phải toàn bộ file Gradle độc lập. Với Maven, dùng các starter tương ứng do Spring Boot BOM quản lý.

### 5.2. Controller tạo và đọc sách

Tạo file **`src/main/java/demo/created/CreatedApplication.java`**:

```java
package demo.created;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class CreatedApplication {

    public static void main(String[] args) {
        SpringApplication.run(CreatedApplication.class, args);
    }
}

record CreateBookRequest(@NotBlank String title) {}

record BookResponse(long id, String title) {}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final AtomicLong nextId = new AtomicLong(1000);
    private final ConcurrentMap<Long, BookResponse> books =
            new ConcurrentHashMap<>();

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        long id = nextId.incrementAndGet();
        BookResponse saved = new BookResponse(id, request.title());
        books.put(id, saved);

        URI location = URI.create("/api/books/" + id);
        return ResponseEntity.created(location).body(saved);
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    BookResponse findById(@PathVariable long id) {
        BookResponse result = books.get(id);
        if (result == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return result;
    }
}
```

Đây là **một tệp Java hợp lệ** với đúng một public class (`CreatedApplication`). Hai record và controller không có `public` nên có thể khai báo cùng tệp; Spring Boot component scan từ package `demo.created` sẽ nhận controller.

Các quyết định trong ví dụ:

1. `@NotBlank` và `@Valid` ngăn POST với `title=null`, `""` hoặc chỉ có khoảng trắng. Đây là validation cú pháp/đầu vào, không phải toàn bộ business rules.
2. `AtomicLong` cung cấp ID khác nhau trong một JVM khi nhiều request đồng thời; sau restart ID có thể lặp vì ví dụ chỉ lưu trong bộ nhớ.
3. `books.put(id, saved)` ghi tài nguyên **trước khi trả 201**. Trạng thái 201 chỉ có ý nghĩa khi server thực sự xử lý tạo thành công theo mô hình đang dùng.
4. `URI.create("/api/books/" + id)` xây **Location tương đối theo root của origin**. Vì ID là số server sinh, không có dữ liệu chuỗi chưa encode chèn trực tiếp vào URI.
5. `ResponseEntity.created(location).body(saved)` trả đúng `201` + `Location` + JSON DTO. API không trả JPA Entity nội bộ.
6. `GET /api/books/{id}` trả 200 nếu có sách, ném `ResponseStatusException(404)` nếu không tồn tại. Client có thể dựa vào Location để truy vấn.
7. Ví dụ giả định web app triển khai ở **root context path**; nếu chạy dưới `/myapp` hoặc sau gateway đổi prefix, phải điều chỉnh chính sách xây URI ở phần 8.

**Không xem ConcurrentHashMap là database:** không có persistence, transaction, uniqueness toàn hệ thống, audit, backup hoặc chia sẻ state giữa nhiều instance. Nếu dùng DB, cần lưu transactionally rồi xây Location dựa trên ID thực tế.

### 5.3. Chạy và thử với curl

Khởi động project Gradle:

```bash
./gradlew bootRun
```

Gửi POST:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":"Spring MVC thực hành"}'
```

Trong ứng dụng demo mới khởi động và chưa có POST nào khác, phản hồi điển hình:

```http
HTTP/1.1 201
Location: /api/books/1001
Content-Type: application/json

{"id":1001,"title":"Spring MVC thực hành"}
```

Header khác như `Date`, `Connection`, `Content-Length` hoặc charset được bỏ khỏi ví dụ. **ID 1001 chỉ đúng nếu chưa có request tạo trước đó**; thứ tự field trong JSON không phải cam kết. Thực tế cần lấy Location từ phản hồi, không đoán ID.

Đọc tài nguyên:

```bash
curl -i 'http://localhost:8080/api/books/1001'
```

Kết quả thông thường:

```http
HTTP/1.1 200
Content-Type: application/json

{"id":1001,"title":"Spring MVC thực hành"}
```

Kiểm tra body không hợp lệ:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
```

Thông thường nhận **400 Bad Request** do `@NotBlank`; không có sách nào được tạo và **không trả Location mới**. JSON error body cụ thể phụ thuộc `@ControllerAdvice`/Boot error configuration và không phải một phần cố định của ví dụ.

Nếu dùng Postman, Bruno hoặc fetch trong browser, cần kiểm tra trực tiếp **status và response header Location**. Một `201` không tự động làm công cụ điều hướng sang trang mới.

## 6. Kiểm thử đúng contract POST → 201 + Location → GET

Kiểm thử cần xác nhận đồng thời:

- POST dữ liệu hợp lệ trả `201 Created`.
- Có header `Location` đúng dạng.
- Body chứa dữ liệu đã lưu và ID do server tạo.
- GET tới URI nhận từ Location trả tài nguyên mới.
- POST không hợp lệ trả lỗi và **không báo thành công**.

Trong dự án Boot 3 ở phần 5, tạo **`src/test/java/demo/created/CreatedApplicationTests.java`**:

```java
package demo.created;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CreatedApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void createsResourceAndCanRetrieveAtLocation() throws Exception {
        MvcResult created = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Spring MVC"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Spring MVC"))
            .andReturn();

        String location =
                created.getResponse().getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertTrue(location.matches("/api/books/[0-9]+"));

        mvc.perform(get(location).accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void invalidInputDoesNotCreateResource() throws Exception {
        MvcResult invalid = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"   "}
                    """))
            .andExpect(status().isBadRequest())
            .andReturn();

        String location =
                invalid.getResponse().getHeader(HttpHeaders.LOCATION);
        org.junit.jupiter.api.Assertions.assertNull(location);
    }

    @Test
    void absentResourceReturns404() throws Exception {
        mvc.perform(get("/api/books/9223372036854775807"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
./gradlew test
```

Với bản demo dùng Boot 3, `spring-boot-starter-test` và `spring-boot-starter-validation` như mô tả, **ba bài test dự kiến pass**. Đây là kỳ vọng theo code, chưa phải output từ một lần chạy cụ thể. Các test không lệ thuộc ID cố định giữa các bài; vì vậy có thể chạy lặp lại khi `AtomicLong` tiếp tục tăng.

Hạn chế của `MockMvc`: nó chạy qua Spring MVC với Spring test mock request/response, **không đi qua reverse proxy hoặc network browser thực tế**. Để xác minh absolute URL/forwarded headers, cần thêm integration test trong môi trường có proxy tin cậy và base URL production.

### Test khi không trả body

Nếu API chủ động chọn 201 không body, đổi method thành:

```java
ResponseEntity<Void> create(...) {
    URI location = ...;
    return ResponseEntity.created(location).build();
}
```

Đây là fragment thiết kế khác, dấu `...` chỉ là placeholder của chữ ký/logic, **không phải Java compilable độc lập**. Khi test, bỏ assertion JSON body; giữ assertion `status().isCreated()` và header `Location`. Có thể dùng `content().string("")` nếu contract thực sự yêu cầu body rỗng.

## 7. Xây URI Location: đường dẫn tương đối hay URL tuyệt đối?

### 7.1. Relative Location

```java
URI location = URI.create("/api/books/" + saved.id());
return ResponseEntity.created(location).body(saved);
```

Đây là lựa chọn đơn giản khi API có root path cố định trên cùng origin. RFC 9110 cho phép `Location` là **URI-reference**, không bắt buộc chứa scheme/host. Client đang gửi POST tới `https://api.example.com/api/books` có thể resolve `/api/books/1001` thành `https://api.example.com/api/books/1001`.

Ưu điểm: không lấy hostname từ một header không đáng tin, giảm vấn đề HTTP/HTTPS khi sau proxy. Rủi ro: URI bắt đầu bằng `/` trỏ về **root của host**, vì thế nếu API có context path `/catalog` hoặc gateway công bố prefix `/v1`, Location phải bao gồm prefix công khai thích hợp (ví dụ `/catalog/api/books/1001`). Nếu cần URL dưới **chính thư mục URI hiện tại**, hiểu đúng quy tắc resolve của relative path như `1001` so với path kết thúc slash; tránh ghép chuỗi tùy tiện.

### 7.2. Absolute Location do ứng dụng biết trước

Nếu API được công bố ở hostname chuẩn cố định, có thể dựng từ cấu hình được quản lý:

```java
// Chỉ minh họa: giá trị này nên đến từ config tin cậy.
URI location = URI.create(
        "https://api.example.com/api/books/" + saved.id());
```

Lựa chọn này hữu ích khi service chạy sau reverse proxy và phải đảm bảo Location trỏ tới hostname public. Không hardcode hostname môi trường dev/staging trong business logic; đưa base URL vào configuration. Không dùng request `Host` hoặc `X-Forwarded-Host` không được xác thực để tự dựng Location tuyệt đối, vì có thể tạo link độc hại trong response (*host-header poisoning*).

### 7.3. Sử dụng `ServletUriComponentsBuilder` trong Spring MVC

Trong ứng dụng Servlet, khi muốn dựng URL dựa trên request hiện tại:

```java
import java.net.URI;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

URI location = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .pathSegment("{id}")
        .buildAndExpand(saved.id())
        .toUri();
```

Đây là **fragment trong request-handling method**, giả định request hiện tại là `POST /api/books`, không có trailing slash/prefix đặc biệt và biến `saved` đã có. Khi gọi, builder dùng scheme/host/path từ request, nối path segment ID, nên URL có thể dạng `http://localhost:8080/api/books/1001`. Cách này thường tự giữ context path theo request đã được Servlet container cung cấp.

Các lưu ý:

- Nếu request path đã kết thúc bằng `/`, cần xem đầu ra thực tế để tránh canonical URL có slash kép/ngoài ý muốn.
- Reverse proxy có thể đổi scheme/host/prefix; cấu hình trusted forwarded headers và `ForwardedHeaderFilter`/cơ chế container thích hợp nếu cần. Không tin headers do client công khai gửi trực tiếp.
- `fromCurrentRequestUri()` dùng request URI, không thêm query string để tạo Location; nên kiểm tra kết quả nếu request có `?source=...`.
- Khi ID là **chuỗi slug** lấy từ input thay vì số server cấp, phải encode theo **URI path segment**, tránh chèn thẳng slash, `?`, `#` hoặc percent-encoded string chưa kiểm soát.

### 7.4. URI path segment có ký tự đặc biệt

Nếu identifier là chuỗi, ưu tiên URI builder có template variable:

```java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

String slug = "spring mvc/advanced";
URI location = UriComponentsBuilder
        .fromPath("/api/books")
        .pathSegment("{slug}")
        .encode()
        .buildAndExpand(slug)
        .toUri();
```

Trong tình huống này slash **nằm trong giá trị slug**, nên được encode như dữ liệu của **một segment**, không tách thành cấp đường dẫn mới. Nếu hệ thống chủ động cho phép slug nhiều segment, đó là thiết kế route khác và cần được nêu rõ. Giá trị `slug` chỉ minh họa; trong API thật, kiểm tra tính hợp lệ và uniqueness tại nơi cấp định danh.

**Không dựng Location bằng nối chuỗi từ dữ liệu request không kiểm soát**. Đặc biệt tránh gắn input nguyên bản vào URL có thể chứa `#`, `?` hoặc chuỗi gây thao túng path.

## 8. Điều gì cần hoàn tất trước khi trả 201?

`201` có ý nghĩa quan sát được khi tài nguyên **đã tạo thành công** theo hợp đồng. Với repository hoặc database:

1. Validate input.
2. Thực thi business rules và authorization.
3. Tạo entity mới, persist qua transaction thích hợp.
4. Nhận identifier thực đã được hệ thống lưu trữ cấp.
5. Xây URI của tài nguyên từ identifier đó.
6. Trả `201 Created` cùng `Location` và body khi cần.

Pseudocode:

```java
@PostMapping
ResponseEntity<BookView> create(@Valid @RequestBody CreateBookRequest dto) {
    Book saved = bookService.createBook(dto); // service quản lý transaction
    URI location = URI.create("/api/books/" + saved.getId());
    return ResponseEntity.created(location)
            .body(BookView.from(saved));
}
```

Đây là **fragment thiết kế service/DTO**, không tự biên dịch: `Book`, `bookService` và `BookView.from` là thành phần application phải định nghĩa. Điểm mấu chốt là location lấy từ **ID đã được cấp và xác nhận lưu**. Không trả 201 chỉ vì đã *bắt đầu* gọi lưu, rồi chạy công việc thật trong background có thể thất bại.

Đối với một transaction database thông thường, bảo đảm lỗi commit được xử lý trước khi chốt thành công HTTP. Nếu dùng outbox/eventual consistency, định nghĩa rõ tài nguyên nào đã tạo: ví dụ request/task resource có thể được tạo ngay (201 cho task), trong khi sản phẩm cuối còn xử lý (202/khác theo thiết kế). Không báo tài nguyên cuối đã tạo nếu mới gửi event.

### ID do client cung cấp bằng PUT

Với `PUT /api/books/book-abc`, URI đã do client chỉ định:

- Nếu tài nguyên `book-abc` chưa tồn tại và PUT tạo mới: **201 Created**.
- Nếu đã tồn tại và PUT cập nhật/thay thế: **200 OK** với body hoặc **204 No Content**.
- `Location` trong 201 có thể là URI đích `/api/books/book-abc` để làm rõ tài nguyên mới; tùy hợp đồng.

**Không dùng POST và PUT như từ đồng nghĩa.** POST yêu cầu server xử lý theo semantics của collection/resource, thường để server cấp URI; PUT yêu cầu trạng thái tại **target URI đã biết** và là phương thức idempotent theo HTTP semantics, dù side effects phụ trợ cần được thiết kế cẩn thận.

## 9. POST, retry và nguy cơ tạo trùng

POST **không mặc định idempotent**. Nếu client gửi POST tạo tài nguyên rồi network timeout trước khi nhận 201, client có thể không biết server đã tạo thành công. Gửi lại POST giống hệt có thể tạo **một tài nguyên thứ hai**, ví dụ ID 1002, và trả thêm một 201 khác.

```text
Client                          Server
  | POST /api/books              |
  |----------------------------->| tạo id=1001
  |          201 Location        |
  |<----------[timeout]----------| phản hồi bị mất
  | POST /api/books (retry)      |
  |----------------------------->| tạo id=1002 nếu không chống trùng
  | 201 Location: /api/books/1002|
  |<-----------------------------|
```

Phương án thường dùng: **Idempotency-Key** do client sinh cho một ý định tạo mới, kết hợp với kho lưu idempotency ở server. Một thiết kế tốt cần:

- Scope khóa theo user/tenant, endpoint/action, không dùng chung bừa bãi toàn hệ thống.
- Giới hạn thời gian sống; lưu khóa và kết quả một cách atomic hoặc có cơ chế coordination phù hợp.
- Nếu cùng khóa và cùng payload được gửi lại, trả kết quả đã ghi nhận (có thể gồm cùng `201`, `Location` và body), theo hợp đồng API.
- Nếu cùng khóa nhưng payload khác, báo xung đột (`409` hay lỗi phù hợp) thay vì âm thầm tái sử dụng kết quả.
- Giữ unique constraint/business constraints trong DB để tránh race condition.
- Không coi chỉ việc thêm header `Idempotency-Key` là đã có idempotency; backend phải triển khai semantics.

Đây là một mẫu thiết kế API, không phải khả năng tự động của `ResponseEntity.created(...)` hoặc Spring MVC. Với thao tác tạo có chi phí cao như thanh toán hoặc cấp tài nguyên, idempotency và xử lý retry là phần quan trọng của hợp đồng.

## 10. Khi nào Location không được truy xuất ngay?

Ngay cả khi `201` đúng về mặt ngữ nghĩa, client có thể không GET được Location tức thì do các yếu tố như:

- API không hỗ trợ GET tài nguyên vừa tạo vì policy/authorization (nên tài liệu cần nói rõ).
- Tài nguyên được persist nhưng bản đọc qua replica/search index cập nhật chậm; đây là **eventual consistency**, cần thiết kế lại kỳ vọng read-after-write hoặc cung cấp endpoint đảm bảo nhất quán.
- API gateway có prefix route khác, Location sai context path hoặc scheme/host.
- Backend tạo resource ở một service khác nhưng chỉ trả URI nội bộ không công khai.
- URI có ID chứa ký tự đặc biệt nhưng chưa được percent-encode đúng.
- Tài nguyên được tạo thành công nhưng ngay sau đó bị xóa hoặc user mất quyền đọc.

Nếu hệ thống hứa “GET ngay lập tức đến Location sau 201 sẽ thấy tài nguyên” thì cần kỹ thuật đủ đáp ứng (read-your-writes) và integration test để giữ cam kết. Trong hệ thống eventual consistency, chỉ trả 201 vẫn có thể đúng nếu tài nguyên thực sự đã được tạo, nhưng **contract cần giải thích khi nào có thể đọc và cách client theo dõi**.

## 11. Sai sót thường gặp trong Spring MVC

### A. Dùng `ResponseEntity.ok` mặc định sau khi tạo

```java
// Không thể hiện semantics "đã tạo tài nguyên mới".
return ResponseEntity.ok(saved);
```

Cách sửa cho endpoint POST tạo tài nguyên:

```java
return ResponseEntity.created(location).body(saved);
```

Không phải mọi POST đều cần 201; các POST điều khiển tác vụ hoặc query có thể trả 200/204. Cần xét **kết quả thực tế của operation**.

### B. Có 201 nhưng không có Location khi ID do server cấp

```java
@ResponseStatus(HttpStatus.CREATED)
@PostMapping
public BookResponse create(@RequestBody CreateBookRequest request) {
    // ...
}
```

Đoạn này không tự tạo Location. Nếu POST vào collection và tạo item con, client không có URI canonical rõ ràng. Chuyển sang `ResponseEntity.created(...)` hoặc tự thêm header dựa trên ID lưu thật.

### C. Header Location trỏ sai

Sai ví dụ: `Location: /api/books` sau khi server vừa tạo `/api/books/1001`. Client có thể hiểu collection là tài nguyên chính. Nếu cần trỏ client đến collection để tham khảo thêm, có thể đặt link ở response body hoặc header `Link` với relation phù hợp, nhưng `Location` của 201 nên xác định đúng primary created resource.

### D. Tạo URI trước khi có ID

```java
long id = 1001L; // hardcode nhầm từ tài liệu demo
repository.save(entity);
return ResponseEntity.created(URI.create("/api/books/" + id)).build();
```

Trong production, ID có thể được DB/generator cấp; hardcode hoặc dự đoán ID trước save là sai. Truyền ID được lưu thật, có xử lý lỗi persistence.

### E. Sử dụng địa chỉ server nội bộ hoặc tin Host từ client

Ví dụ server ở `http://10.0.0.15:8080` sau public proxy `https://api.example.com` nhưng trả Location nội bộ: client bên ngoài không truy cập được, có nguy cơ lộ topology. Phân biệt:
- URI relative với prefix public đúng.
- Absolute URI lấy từ cấu hình external base URL tin cậy.
- Forwarded headers được trust đúng proxy chain nếu dựng URI từ request.

### F. Trả 201 dù validation, authorization hoặc DB insert thất bại

Một lỗi trong transaction sau khi tạo response body có thể khiến API tuyên bố sai trạng thái. Không chỉ nhìn vào method return trong một service asynchronous; phải chắc chắn công việc tạo đã đạt điều kiện “hoàn tất” được contract định nghĩa.

### G. Nhầm 201 với 303

`303 See Other` có mục đích chuyển client qua một URI khác, thường để GET biểu diễn kết quả POST (ví dụ redirect-after-post). `201` mô tả tài nguyên được tạo và Location xác định URI đó, nhưng client **không tự redirect**. Không trộn semantics khi test.

### H. Trả JPA entity thẳng vào JSON body

Entity có thể gồm field nội bộ, lazy relationship, vòng tham chiếu hoặc thông tin nhạy cảm. Nên chọn response DTO (`BookResponse`) với các field công khai và giữ chuẩn output JSON riêng.

## 12. Thiết kế response body và thông tin đi kèm

Body trong 201 thường là lựa chọn thiết kế sản phẩm; có vài mẫu phổ biến:

| Mẫu | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| `201` + Location + full DTO | `{"id":1001,"title":"Spring MVC"}` | Client cần sử dụng ngay tài nguyên mới |
| `201` + Location + summary DTO | `{"id":1001}` | Muốn payload nhẹ, client tự GET khi cần |
| `201` + Location + không body | Không có body | Client chỉ cần URI, schema API quy định vậy |
| `201` + Location + metadata | DTO kèm trạng thái ban đầu hoặc version | Tạo thành công nhưng workflow có các bước tiếp theo |

Các header bổ sung:

- **`ETag`**: nếu được cung cấp và phản ánh representation hiện tại, client có thể dùng conditional requests như `If-Match` khi cập nhật; giúp tránh lost update. Không tự động được tạo khi gọi `ResponseEntity.created`.
- **`Content-Location`**: chỉ ra URI của representation trong body như đã giải thích ở phần 2.
- **`Cache-Control`**: nếu response chứa dữ liệu nhạy cảm hoặc chính sách caching cụ thể; không tự suy rằng mọi 201 có thể cache theo default.
- **`Link`**: có thể nêu tài nguyên liên quan như collection, owner hay next action, theo media type/API contract.

Ví dụ Java method có version nếu service cung cấp:

```java
return ResponseEntity.created(location)
        .eTag("\"v1\"")
        .body(saved);
```

Đây là fragment trong method controller, chỉ hợp lệ nếu `saved` và `location` đã định nghĩa, đồng thời version token `"v1"` thực sự tương ứng representation lưu. ETag trong ví dụ chỉ để thấy cú pháp; **không hardcode một ETag cho mọi tài nguyên** trong ứng dụng thật.

## 13. Phân biệt lỗi HTTP khi POST tạo mới

Trong ứng dụng thật nên có API error contract rõ ràng. Ví dụ:

| Trường hợp | HTTP status thường chọn | Lý do |
| --- | --- | --- |
| JSON malformed | `400 Bad Request` | Không deserialize được request |
| Thiếu `title` bắt buộc | `400 Bad Request` | Vi phạm validation khi binding |
| `Content-Type: text/plain` nhưng endpoint chỉ consumes JSON | `415 Unsupported Media Type` | Converter/mapping không hỗ trợ media type |
| `Accept: application/xml` nhưng endpoint chỉ produces JSON | `406 Not Acceptable` | Không có representation phù hợp |
| Unique key của tên sách bị trùng, hợp đồng không cho trùng | `409 Conflict` | Trạng thái hiện tại xung đột |
| User chưa đăng nhập / không đủ quyền | `401` / `403` | Security từ chối |
| Service phụ trợ tạm thời không sẵn sàng | `503 Service Unavailable` khi phù hợp | Không báo tạo thành công |
| POST tạo được sách | `201 Created` | Cần Location của sách mới |
| POST enqueue tác vụ chưa hoàn tất | `202 Accepted` | Theo dõi trạng thái bất đồng bộ |

Không nên “fix” mọi trường hợp về HTTP 200/201 rồi đưa `success=false` trong body. Client, proxy, monitoring và SDK dựa nhiều vào status; dùng status đúng giúp hợp đồng rõ và hệ sinh thái HTTP vận hành chính xác.

### Xử lý exception trong Spring MVC

Với REST API, `@RestControllerAdvice` và `@ExceptionHandler` (hoặc `ResponseEntityExceptionHandler`/`ProblemDetail` từ Spring Framework 6+) có thể thống nhất response lỗi. Tuy nhiên:
- Không thêm `Location` tài nguyên mới vào response lỗi chưa tạo gì.
- Không gửi stack trace, SQL statement hay ID nội bộ nhạy cảm về client.
- Khi unique constraint race xảy ra, phân loại lỗi DB cụ thể thành conflict chỉ khi chắc chắn phù hợp, không chuyển toàn bộ `DataIntegrityViolationException` sang 409 mù quáng.
- Nếu idempotency request đã tạo trước đó nhưng response bị mất, xử lý retry theo contract để client lấy lại URI tài nguyên cũ.

## 14. Phiên bản Spring và sự tương thích của API

| Mốc | `ResponseEntity.created(URI)` | Ghi chú |
| --- | --- | --- |
| Spring Framework 5.x, Boot 2.x | Có | Ứng dụng Boot 2 thường dùng `javax.validation` |
| Spring Framework 6.x, Boot 3.x | Có | Ví dụ đầy đủ bên trên dùng `jakarta.validation`, Java 17+ |
| Spring Framework 7.x, Boot 4.x | Có | Builder 201 + Location vẫn tồn tại; một số module/starter và hệ sinh thái Jackson/validation có thay đổi |

Cơ chế 201/Location thuộc **HTTP semantics**, không phụ thuộc Jackson 2 hay Jackson 3. Nếu migrate Boot 3 → Boot 4, cần cập nhật imports/dependencies theo framework, nhưng API cấp HTTP `ResponseEntity.created(location)` vẫn giúp biểu diễn hợp đồng rõ ràng.

Mốc Spring Framework 6.0/7.0 có thể đổi hành vi URL matching hoặc converter, nên cần chạy lại test URI trong `Location` và GET endpoint. **Không tự tạo URI có slash cuối** rồi mặc định rằng router `@GetMapping("/api/books/{id}")` sẽ nhận cả hai dạng khi cấu hình path matching không cho phép.

## 15. Checklist kiểm tra trước khi công bố endpoint tạo mới

- [ ] Endpoint thực sự tạo tài nguyên trước khi trả `201`; nếu chỉ enqueue, cân nhắc `202`.
- [ ] Trả `ResponseEntity.created(location)` hoặc tương đương; Location xác định đúng primary resource.
- [ ] Location là URI reference hợp lệ, có encode path segments và base path/public prefix đúng.
- [ ] Location không leak private host, không thể bị giả mạo qua Host/Forwarded headers không đáng tin.
- [ ] Nếu API cam kết GET tại Location, endpoint GET có thể đọc tài nguyên đúng ID theo consistency policy.
- [ ] Contract body rõ: trả DTO đầy đủ, summary hay rỗng; `Content-Type` đúng khi body JSON.
- [ ] Validation/auth/DB conflict thất bại thì không trả 201; bảo vệ uniqueness và transaction.
- [ ] Retry POST được thiết kế có chủ ý, nhất là thao tác thanh toán hoặc tạo có chi phí lớn.
- [ ] Có test `POST → 201 + Location → GET`, test invalid 400, conflict, auth và proxy prefix khi cần.
- [ ] Không hardcode ID/host của ví dụ vào production.
- [ ] Đã cập nhật OpenAPI/SDK và tài liệu client về response 201, header Location, body và các lỗi.

## 16. Bài tập và câu hỏi tự đánh giá

1. **HTTP semantics:** POST tạo thành công một tài nguyên tại `/api/tasks/42`. Vì sao `201` cần đi kèm Location để client dễ sử dụng? `201` có bắt buộc body JSON không?
2. **Phân biệt redirect:** Vì sao trình duyệt không tự GET `Location` trên phản hồi `201` nhưng có thể chuyển hướng sau `303`?
3. **Spring API:** Viết controller `create` trả `ResponseEntity.created(uri).body(dto)` và một GET matching. Kiểm thử status, header và body.
4. **Validation:** Khi `title=""` gây 400, liệu Location trỏ tới `/api/books/1001` có phù hợp không? Giải thích.
5. **URI encoding:** Nếu slug tài nguyên là `"spring web/101"`, tại sao ghép trực tiếp thành path là sai? Dùng builder với `pathSegment`.
6. **Reverse proxy:** App chạy nội bộ `http://localhost:8080` nhưng public URL là `https://api.example.com/v1`. Hãy thiết kế Location nhất quán và kiểm thử forwarded-header trust policy.
7. **Retry:** Client timeout sau POST, gửi lại và tạo bản ghi thứ hai. Hãy thiết kế một Idempotency-Key contract xử lý cùng key/cùng payload/khác payload.
8. **Transaction:** DB phát sinh unique conflict lúc commit. Nếu controller đã chuẩn bị response 201 nhưng commit thất bại, client cần nhận status nào và vì sao?
9. **201 hay 202:** API nhận yêu cầu tạo báo cáo, thực tế cần vài phút mới xây xong. Nếu có job resource được tạo ngay, status nào mô tả **job**? Status nào mô tả **báo cáo cuối** đang chờ? Cần phân biệt hai tài nguyên.
10. **PUT:** Với `PUT /api/books/client-id-1`, lần đầu tạo mới và lần hai cập nhật, hãy chọn status theo RFC 9110 và viết test cho hai lần gọi.

## 17. Tài liệu tham khảo chính thức

- [RFC 9110, `15.3.2 — 201 Created](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.2): ngữ nghĩa 201 và primary resource.
- [RFC 9110, `10.2.2 — Location](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.2): URI-reference, ý nghĩa Location của 201 và 3xx.
- [RFC 9110, `8.7 — Content-Location](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.7): khác biệt giữa Location và Content-Location.
- [RFC 9110, `9.3.4 — PUT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.4): thành công khi tạo mới so với cập nhật target resource.
- [Spring Framework 6.x Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/http/ResponseEntity.html): `created(URI)` và các builder HTTP.
- [Spring Framework 7 Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): `created(URI)` vẫn hiện diện.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): phản hồi `ResponseEntity` trong MVC.
- [Spring Framework — ServletUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html): dựng URI từ request Servlet.
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): xử lý template, path segment và encoding.
