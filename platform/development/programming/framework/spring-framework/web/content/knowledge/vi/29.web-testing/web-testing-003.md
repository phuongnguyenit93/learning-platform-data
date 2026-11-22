# Kiểm chứng mapping, tham số, header, status và nội dung JSON trong Spring Web

## 1. Mục tiêu kiểm thử một HTTP endpoint

Một endpoint Spring Web đúng không chỉ là phương thức Java trả về đối tượng đúng. Nó phải nhận **đúng HTTP method và URL**, ánh xạ **path variable, query parameter, request header và request body** vào tham số Java, tạo **status code**, **response headers** và **JSON body** đúng hợp đồng. Kiểm thử web xác minh các điều này qua HTTP request/response ở tầng Spring MVC hoặc Spring WebFlux.

Ví dụ hợp đồng cần bảo vệ:

~~~http
GET /api/books/7?lang=en
X-Tenant: school
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
X-Tenant-Echo: school

{"id":7,"title":"Spring","language":"en"}
~~~

Không nhất thiết test mỗi dòng bằng một test riêng, nhưng trong cả bộ test phải kiểm tra được:

1. **Mapping:** request GET /api/books/7 có đi vào đúng controller method, còn sai method/path trả status phù hợp không?
2. **Tham số:** **7** trở thành tham số **@PathVariable long id**, **lang=en** đi vào **@RequestParam**, header **X-Tenant** đi vào **@RequestHeader**?
3. **Request contract:** client gửi đúng **Content-Type**, **Accept**, body JSON, hoặc thiếu/nhập sai thì server xử lý thế nào?
4. **Response contract:** status là 200/201/400/404/405/415/406 theo trường hợp, header **Location**, **Content-Type** và các header nghiệp vụ có đúng không?
5. **JSON:** các trường, giá trị, cấu trúc object/array, kiểu số/chuỗi có đúng không? Có vô tình trả một đối tượng lỗi với HTTP 200 không?

Trong Spring, nên kiểm thử cả **happy path** và **negative path**. Đừng dừng ở **status().isOk()**: một controller sai mapping hoặc trả JSON sai schema vẫn có thể trả 200.

## 2. Chọn công cụ và mức kiểm thử

Spring hỗ trợ hai công cụ nổi bật:

- **MockMvc** dành cho **Spring MVC** (Servlet stack). Nó chạy qua hạ tầng Spring MVC và tạo mock request/response, **không mở HTTP server thật**. Nó đặc biệt hữu ích để xác minh controller mapping, argument resolver, validation, message converter, exception handler, response status và JSON.
- **WebTestClient** là HTTP test client với API fluent; dùng được với **Spring WebFlux** và cũng có thể test **Spring MVC** (qua **MockMvcWebTestClient**), hoặc chạy end-to-end với server thật. Nó kiểm tra response bằng **expectStatus**, **expectHeader** và **expectBody**.

| Mức kiểm thử | Cách khởi tạo | Điều được kiểm chứng | Điều chưa bao phủ |
| --- | --- | --- | --- |
| Controller unit test bằng gọi method Java | new Controller(...).method(...) | Logic Java thuần | HTTP mapping, binding, converter, status/headers thực |
| **MockMvc standalone** | MockMvcBuilders.standaloneSetup(controller) | Mapping/binding/response với MVC cấu hình cục bộ | Không tự nạp mọi filter, advice, custom converter của app |
| **@WebMvcTest** + MockMvc | Spring Boot MVC slice | Controller, MVC infrastructure và cấu hình thuộc slice | Không nạp toàn bộ service/repository của ứng dụng |
| **@SpringBootTest** + MockMvc | Full ApplicationContext + mock servlet | Tích hợp rộng gồm beans/filter/application wiring | Không xác minh HTTP network thật |
| **WebTestClient.bindToController** | WebFlux mock setup | WebFlux router/controller và response reactive | Network/proxy thực |
| **MockMvcWebTestClient.bindToController** | MVC mock setup | MVC dùng cú pháp WebTestClient | Network thực |
| **WebTestClient.bindToServer** | Kết nối server đang chạy | HTTP end-to-end, network stack | Chậm hơn, cần server/test environment |

**Khuyến nghị cho bài học:** dùng **@WebMvcTest + MockMvc** để học từng assertion MVC, sau đó dùng **WebTestClient** nếu dự án dùng WebFlux hoặc muốn test thông qua API HTTP client thống nhất. Đừng thay HTTP-level test bằng cách gọi trực tiếp method controller: khi đó **@GetMapping**, **@PathVariable**, **@RequestBody** và chuyển JSON không được thực thi.

## 3. Thiết kế controller và hợp đồng trước khi viết test

Giả sử ứng dụng cung cấp hai endpoint:

- **GET /api/books/{id}?lang=...** bắt buộc header **X-Tenant**. Chỉ sách id=7 tồn tại, có thể chọn language, và server echo tenant qua response header.
- **POST /api/books** yêu cầu **Content-Type: application/json** với body **{"title":"..."}**, trả **201 Created**, **Location: /api/books/8** và body mô tả sách đã tạo.

Một phiên bản controller Java 17:

~~~java
package demo;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/api/books",
                produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {
    public record BookView(long id, String title, String language) {}
    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public ResponseEntity<BookView> getBook(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi") String lang,
            @RequestHeader("X-Tenant") String tenant) {

        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok()
            .header("X-Tenant-Echo", tenant)
            .body(new BookView(7, "Spring", lang));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @RequestBody CreateBook request) {
        return ResponseEntity.created(URI.create("/api/books/8"))
            .body(new BookView(8, request.title(), "vi"));
    }
}
~~~

**Những điểm cần chứng minh qua test:**

- **@RequestMapping(path=..., produces=...)** đặt path chung và media type đầu ra. Hai annotation method bổ sung điều kiện GET/POST và path.
- **@PathVariable("id") long** kiểm tra đường dẫn và chuyển chuỗi sang số. Chuỗi không chuyển được thành long dẫn đến lỗi binding, thường HTTP 400.
- **@RequestParam(name="lang", defaultValue="vi")** dùng "vi" khi thiếu query parameter; nếu có **lang=en** phải nhận "en".
- **@RequestHeader("X-Tenant")** mặc định **required=true**; thiếu header thường trả 400 do Spring MVC xử lý, trước khi code nghiệp vụ chạy.
- **@PostMapping(consumes="application/json")** chỉ khớp request có content type phù hợp. Gửi **text/plain** thường trả HTTP 415.
- **ResponseEntity** định rõ status và header. **created(...)** đặt HTTP 201 và Location; body record được Jackson serialize thành JSON.
- **@RestController** tự viết response body qua converter. Nếu dùng **@Controller** thông thường mà thiếu **@ResponseBody**, String return value có thể được hiểu là view name.

Đây là ví dụ có trạng thái cố định để test có tính quyết định. Trong hệ thống thật, controller thường gọi service/repository; khi đó mock service trong MVC slice và xác minh cả input truyền tới service.

## 4. MockMvc: cấu trúc một assertion đúng

Cách đọc một test MockMvc:

~~~java
mockMvc.perform(
        get("/api/books/{id}", 7)
            .param("lang", "en")
            .header("X-Tenant", "school")
            .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(handler().handlerType(BookController.class))
    .andExpect(handler().methodName("getBook"))
    .andExpect(header().string("X-Tenant-Echo", "school"))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value(7))
    .andExpect(jsonPath("$.title").value("Spring"))
    .andExpect(jsonPath("$.language").value("en"));
~~~

Ở đây **get(...)** là request builder từ **MockMvcRequestBuilders**, không phải gọi method Java trực tiếp.

- **perform(...)** chuyển mock HTTP request qua hạ tầng MVC.
- **status().isOk()** xác minh status response là 200.
- **handler().handlerType(...)**, **handler().methodName(...)** xác minh **handler được Spring chọn**. Đây là bằng chứng trực tiếp về mapping khi dùng MockMvc.
- **header().string(...)** đọc **response header**, khác với **.header(...)** ở request builder là đặt **request header**.
- **content().contentTypeCompatibleWith(APPLICATION_JSON)** kiểm tra response media type tương thích JSON; hữu ích nếu server có thêm tham số charset.
- **jsonPath("$.title").value(...)** trích giá trị trong JSON response. **$** là root của JSON document.

Nếu test chỉ có **jsonPath("$.title")**, nó có thể bỏ qua lỗi status hoặc header. Nếu test chỉ có **handler().methodName("getBook")**, nó chưa biết nội dung trả về có đúng. Nên khẳng định những phần là contract, không khẳng định mọi chi tiết implementation nội bộ.

### Mapping là tập hợp nhiều điều kiện

Một mapping Spring MVC có thể phụ thuộc:

- HTTP method: GET, POST, PUT, PATCH, DELETE.
- URL path, template variables, điều kiện **params** và **headers** trong annotation.
- **consumes** (Content-Type của request) và **produces** (tương thích với Accept của client).
- Cấu hình content negotiation, trailing slash và path matching của ứng dụng.

Ví dụ:

~~~java
@GetMapping(path = "/reports",
            params = "format=summary",
            headers = "X-Report-Client=web",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Report summary() {
    return new Report("ready");
}
~~~

Request thiếu **format=summary** hoặc thiếu header có thể **không khớp mapping**, vì điều kiện nằm ở chính **@GetMapping**. Đừng nhầm với trường hợp một method đã khớp nhưng thiếu **@RequestHeader(required=true)**, khi đó Spring phát lỗi binding trước khi method chạy. Các status cụ thể có thể khác theo cấu hình/custom error handler; nên assert theo hợp đồng ứng dụng.

## 5. Kiểm chứng path variable, query parameter và header

### 5.1 Path variable

Giả sử **@GetMapping("/{id}")** với **@PathVariable long id**:

~~~java
mockMvc.perform(get("/api/books/{id}", 7)
        .header("X-Tenant", "school"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7));
~~~

Một vài ca cần có:

- **/api/books/7** → id=7, HTTP 200.
- **/api/books/100** → mapping vẫn khớp nhưng controller trả HTTP 404 do tài nguyên vắng mặt.
- **/api/books/not-a-number** → path vẫn có segment, nhưng chuyển kiểu String sang long thất bại, HTTP 400 theo MVC mặc định.
- **/api/books** không có segment id → không khớp method GET /{id}; với controller có POST /api/books, GET /api/books có thể trả 405, tùy các mapping khác. Không đoán mọi trường hợp đều là 404.

**Không gom 404 từ nghiệp vụ với 404 do không tồn tại route**. Trường hợp id=100 có thể xác minh handler **getBook** đã được chọn và vẫn trả 404; còn route không tồn tại thì không có handler đó.

### 5.2 Query parameter

~~~java
mockMvc.perform(get("/api/books/{id}", 7)
        .param("lang", "en")
        .header("X-Tenant", "school"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.language").value("en"));

mockMvc.perform(get("/api/books/{id}", 7)
        .header("X-Tenant", "school"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.language").value("vi"));
~~~

**.param("lang", "en")** thêm request parameter vào mock request; với GET nó kiểm tra Spring MVC binding của query-like request parameter. Nếu cần kiểm chứng raw query string/URI encoding, gửi URL chứa query thực tế qua builder **get("/api/books?lang=en")** hoặc sử dụng **.queryParam(...)** phù hợp thay vì chỉ kiểm tra dữ liệu sau binding.

Với **@RequestParam(required=true)** không có default, thiếu parameter thường bị Spring MVC trả 400. Với một danh sách, dùng **.param("tag","java","spring")** và Java parameter **List<String>**; cần kiểm tra cả số lượng/thứ tự theo hợp đồng API.

### 5.3 Request header và response header

~~~java
mockMvc.perform(get("/api/books/7")
        .header("X-Tenant", "school")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Tenant-Echo", "school"));
~~~

Đặt request header và assert response header là hai hành động khác nhau. HTTP header names **không phân biệt chữ hoa/thường**, dù convention thường hiển thị kiểu **Content-Type**, **X-Tenant**. Header nghiệp vụ riêng cần test đúng giá trị, nhất là authentication policy, correlation ID, cache metadata, ETag và Location nếu thuộc contract.

Test thiếu header:

~~~java
mockMvc.perform(get("/api/books/7")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isBadRequest());
~~~

Status 400 của ví dụ phát sinh vì **@RequestHeader("X-Tenant")** required mặc định. Với header **@RequestHeader(value="X-Tenant",required=false)**, contract có thể cho phép không gửi; cần test behavior tương ứng. **Accept** diễn đạt dạng response muốn nhận; **Content-Type** diễn đạt dạng request body gửi đi. Đừng assert request header bằng **header().string(...)** (đó là response matcher).

## 6. Kiểm chứng status code đúng ngữ cảnh

| Tình huống | Status kỳ vọng trong demo | Cần kiểm chứng thêm |
| --- | --- | --- |
| GET /api/books/7, đủ header | **200 OK** | Mapping getBook, lang, tenant echo, JSON |
| GET /api/books/100, đủ header | **404 Not Found** | Controller chủ động báo sách không có |
| GET /api/books/not-a-number, đủ header | **400 Bad Request** | Lỗi chuyển path variable sang long |
| GET /api/books/7 thiếu X-Tenant | **400 Bad Request** | Argument resolver từ chối thiếu header |
| POST /api/books với JSON hợp lệ | **201 Created** | Location và JSON mới |
| POST /api/books với JSON cú pháp sai | **400 Bad Request** | JSON converter không đọc được body |
| POST /api/books với text/plain | **415 Unsupported Media Type** | consumes chỉ chấp nhận JSON |
| PUT /api/books/7 | **405 Method Not Allowed** | Có path pattern nhưng method không hỗ trợ |
| GET /api/books/7 với Accept không chấp nhận JSON | **406 Not Acceptable** | produces chỉ khai báo JSON |

**Lưu ý status:** bảng trên gắn với controller và cấu hình mặc định của demo. Một **@ControllerAdvice**, security filter hoặc error handler có thể đổi status/body. Test nên phản ánh contract thực tế đã chọn. HTTP 401/403 phải được tạo bằng chính cơ chế authentication/authorization nếu cần kiểm chứng bảo mật; việc thiếu header nghiệp vụ thông thường **X-Tenant** không tự đồng nghĩa HTTP 401.

Các shortcut của MockMvcResultMatchers:

~~~java
.andExpect(status().isOk());            // 200
.andExpect(status().isCreated());       // 201
.andExpect(status().isBadRequest());    // 400
.andExpect(status().isUnauthorized());  // 401
.andExpect(status().isForbidden());     // 403
.andExpect(status().isNotFound());      // 404
.andExpect(status().isMethodNotAllowed()); // 405
.andExpect(status().isUnsupportedMediaType()); // 415
~~~

Dòng trên là các mệnh đề **minh họa độc lập**, không thể nối tất cả vào cùng một request. Nếu cần status bất kỳ, dùng **status().is(422)** hoặc matcher tương ứng; không hard-code 200 cho mọi route.

## 7. Kiểm chứng JSON: JSONPath và so khớp cấu trúc

JSON response thường là object:

~~~json
{
  "id": 7,
  "title": "Spring",
  "language": "en",
  "meta": {
    "source": "catalog",
    "flags": ["popular", "featured"]
  }
}
~~~

Với MockMvc, các biểu thức JSONPath:

~~~java
.andExpect(jsonPath("$.id").value(7))
.andExpect(jsonPath("$.title").value("Spring"))
.andExpect(jsonPath("$.meta.source").value("catalog"))
.andExpect(jsonPath("$.meta.flags[0]").value("popular"))
.andExpect(jsonPath("$.meta.flags").isArray())
.andExpect(jsonPath("$.meta.flags.length()").value(2));
~~~

**$** là root; **.id** lấy field object; **[0]** là phần tử thứ nhất trong mảng (0-based). Với response là **array ở root**, dùng **$[0].title** thay vì **$.title**.

### JSON type và missing/null

- **jsonPath("$.id").value(7)** kiểm tra giá trị số 7. Một chuỗi **"7"** khác JSON number **7**.
- **jsonPath("$.title").isString()** hoặc **isNotEmpty()** dùng để kiểm tra dạng dữ liệu/không rỗng khi không muốn khóa cứng toàn bộ text.
- **jsonPath("$.meta.flags").isArray()** kiểm tra kiểu array. Các API còn có isMap(), isNumber(), isBoolean(), isEmpty(), exists(), doesNotExist().
- Trường vắng mặt và trường có giá trị **null** khác nhau. **exists()** đòi giá trị khác null; **hasJsonPath()** kiểm tra path tồn tại kể cả null; **doesNotHaveJsonPath()** kiểm tra path không tồn tại. Chọn matcher theo JSON contract cần bảo vệ.

Nếu chỉ muốn so sánh cấu trúc JSON mà không quan tâm whitespace/thứ tự keys:

~~~java
.andExpect(content().json(
    "{\"id\":7,\"title\":\"Spring\",\"language\":\"en\"}"));
~~~

Cách so sánh JSON mang tính cấu trúc. Mặc định ở một số phiên bản Spring, **content().json(...)** dùng kiểu so sánh lenient cho các field không được chỉ định; nếu muốn chặn field thừa hoặc sai kích thước array, hãy dùng strict JSON comparison đúng phiên bản hỗ trợ và test bổ sung. Không so sánh JSON string raw khi mục tiêu chỉ là giá trị trường: thứ tự keys và whitespace có thể đổi mà API vẫn đúng.

**Khi nào dùng JSONPath?** Dùng khi chỉ cần assert vài field ổn định và nhiều metadata có thể thay đổi. **Khi nào kiểm tra toàn body?** Với response error contract hoặc payload nhỏ có schema chặt cần bảo đảm mọi trường, kiểu dữ liệu và mảng.

### Dữ liệu biến động

Với timestamp, ID sinh ngẫu nhiên hoặc request ID:
- Assert trường **tồn tại/đúng định dạng**, không ghi cứng giá trị không ổn định.
- Với trường có thể xác định bằng test fixture, tạo dữ liệu cố định hoặc kiểm soát clock.
- Đừng dùng **Thread.sleep()** để đoán kết quả async; sử dụng API test async/timeout phù hợp.
- Không assert thứ tự của một collection khi hợp đồng không cam kết thứ tự. Nếu API cam kết thứ tự, assert từng phần tử và số lượng.

## 8. Ví dụ Maven + JUnit 5 + @WebMvcTest chạy được (Java 17)

Dự án Spring Boot **3.5.0**, Java 17, Spring MVC và spring-boot-starter-test. Đây là demo kiểm thử tập trung vào mapping/params/headers/status/JSON, không cần DB hay server HTTP bên ngoài.

Cấu trúc file:

~~~text
web-contract-test/
├── pom.xml
├── src/main/java/demo/
│   ├── WebContractApplication.java
│   └── BookController.java
└── src/test/java/demo/
    └── BookControllerTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>web-contract-test</artifactId>
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
</project>
~~~

**src/main/java/demo/WebContractApplication.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebContractApplication.class, args);
    }
}
~~~

**src/main/java/demo/BookController.java**:

~~~java
package demo;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/api/books",
                produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {
    public record BookView(long id, String title, String language) {}
    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public ResponseEntity<BookView> getBook(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi") String lang,
            @RequestHeader("X-Tenant") String tenant) {
        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok()
            .header("X-Tenant-Echo", tenant)
            .body(new BookView(id, "Spring", lang));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @RequestBody CreateBook request) {
        return ResponseEntity.created(URI.create("/api/books/8"))
            .body(new BookView(8, request.title(), "vi"));
    }
}
~~~

**src/test/java/demo/BookControllerTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getMapsPathQueryHeaderAndResponseJson() throws Exception {
        mvc.perform(get("/api/books/{id}", 7)
                .param("lang", "en")
                .header("X-Tenant", "school")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(BookController.class))
            .andExpect(handler().methodName("getBook"))
            .andExpect(header().string("X-Tenant-Echo", "school"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.title").value("Spring"))
            .andExpect(jsonPath("$.language").value("en"));
    }

    @Test
    void missingQueryUsesDefaultLanguage() throws Exception {
        mvc.perform(get("/api/books/7")
                .header("X-Tenant", "school"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"));
    }

    @Test
    void missingRequiredHeaderReturns400() throws Exception {
        mvc.perform(get("/api/books/7"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPathVariableReturns400() throws Exception {
        mvc.perform(get("/api/books/not-a-number")
                .header("X-Tenant", "school"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingBookReturns404() throws Exception {
        mvc.perform(get("/api/books/100")
                .header("X-Tenant", "school"))
            .andExpect(handler().methodName("getBook"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(""));
    }

    @Test
    void postJsonReturns201LocationAndJsonBody() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Java Testing"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", "/api/books/8"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(8))
            .andExpect(jsonPath("$.title").value("Java Testing"))
            .andExpect(jsonPath("$.language").value("vi"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("Java Testing"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void unsupportedMethodReturns405() throws Exception {
        mvc.perform(put("/api/books/7"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

### Chạy ví dụ

Tại thư mục chứa **pom.xml**, với Maven/JDK 17+:

~~~bash
mvn test
~~~

Khi môi trường tải dependency bình thường, Maven Surefire chạy **9 phương thức @Test** trong **BookControllerTest**. Điều kiện đạt là Maven kết thúc với **BUILD SUCCESS** và **Tests run: 9, Failures: 0, Errors: 0, Skipped: 0** (không tính test khác nếu tự bổ sung). Câu này mô tả kết quả kỳ vọng của test suite, không phải log đo được từ một lần chạy trong tài liệu.

Tại sao test không cần chạy server? **@WebMvcTest(BookController.class)** nạp MVC slice và tạo MockMvc, giúp request đi qua DispatcherServlet, handler mapping, argument resolver, message converter và exception resolver bằng mock servlet request/response. Nó không mở cổng 8080 và không gọi Internet.

### Mỗi test thực sự kiểm tra gì?

- **getMapsPathQueryHeaderAndResponseJson**: test một request với path, query, request header; xác nhận MVC chọn method getBook, status 200, response header, media type và ba trường JSON.
- **missingQueryUsesDefaultLanguage**: thực sự chạy binding mặc định của **@RequestParam(defaultValue="vi")**.
- **missingRequiredHeaderReturns400**: chứng minh missing header chặn request ở bước binding, không cần code controller tự kiểm tra.
- **invalidPathVariableReturns400**: chứng minh lỗi convert String → long.
- **missingBookReturns404**: cùng một mapping hoạt động nhưng dữ liệu không tồn tại; khác với route không tìm thấy.
- **postJsonReturns201LocationAndJsonBody**: kiểm tra request JSON decode, HTTP 201, header Location và JSON response.
- **malformedJsonReturns400**: kiểm tra body cú pháp JSON không hợp lệ.
- **wrongRequestContentTypeReturns415**: kiểm tra điều kiện **consumes**.
- **unsupportedMethodReturns405**: xác nhận PUT không nằm trong các method được khai báo cho /api/books/7.

Nếu triển khai controller khác code ví dụ hoặc thêm Spring Security, các status có thể thay đổi do filter/security policy. Khi đó phải khai báo rõ security expectations, ví dụ mock identity và CSRF token, chứ không xóa hết security filter chỉ để test qua.

## 9. Kiểm tra request body, header Location và JSON response có cấu trúc

Có ba hướng cần phân biệt:

**(a) Đặt request body**: dùng **.contentType(APPLICATION_JSON).content(json)** với MockMvc POST/PUT/PATCH. Nếu chỉ gọi **.content(...)** mà không đặt Content-Type, mapping có điều kiện consumes có thể trả 415.

~~~java
mvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Refactoring\"}"))
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", "/api/books/8"))
    .andExpect(jsonPath("$.title").value("Refactoring"));
~~~

**(b) Phân biệt header Location và body field**: status 201 + JSON đúng nhưng thiếu **Location** vẫn có thể vi phạm contract tạo resource. Trong ví dụ server trả Location có đường dẫn tương đối; hệ thống API thực cũng có thể trả absolute URI. Test cần bám vào cách API đã quy định.

**(c) Response body là array hoặc nested object**: áp dụng JSONPath đúng cấu trúc:

~~~json
{
  "data": {
    "items": [
      {"id":7,"title":"Spring"},
      {"id":8,"title":"Java"}
    ]
  },
  "total": 2
}
~~~

Các matcher có thể là:

~~~java
.andExpect(jsonPath("$.total").value(2))
.andExpect(jsonPath("$.data.items").isArray())
.andExpect(jsonPath("$.data.items[0].id").value(7))
.andExpect(jsonPath("$.data.items[1].title").value("Java"));
~~~

Đoạn này là **fragment cho API trả cấu trúc nested như JSON mẫu**, không được gắn nguyên vào test của BookController demo vì controller demo trả BookView phẳng. Kiểm thử contract phải phản ánh JSON thật của endpoint tương ứng.

Đối với nội dung lỗi trả **application/problem+json** theo RFC 9457, JSONPath có thể kiểm tra **type**, **title**, **status**, **detail**, **instance** như hợp đồng; đừng mặc định mọi ứng dụng Spring luôn trả đúng trường đó nếu chưa bật/cấu hình ProblemDetail.

## 10. WebTestClient: cùng hợp đồng, API xác minh khác

Với WebFlux, MockMvc không chạy pipeline của Spring WebFlux. Dùng **WebTestClient**, công cụ hỗ trợ mock server hoặc server thật.

Ví dụ WebFlux controller:

~~~java
@RestController
@RequestMapping("/api/greetings")
class GreetingController {
    record Greeting(String text) {}

    @GetMapping("/{name}")
    Mono<Greeting> greet(
            @PathVariable String name,
            @RequestHeader("X-Lang") String language) {
        return Mono.just(new Greeting(
            language.equals("vi") ? "Xin chào " + name : "Hello " + name));
    }
}
~~~

Đoạn này là **fragment**: cần import **Mono**, **@RestController**, **@RequestMapping**, **@GetMapping**, **@PathVariable**, **@RequestHeader**. Với WebFlux infrastructure, test mock:

~~~java
WebTestClient client =
    WebTestClient.bindToController(new GreetingController()).build();

client.get()
    .uri("/api/greetings/{name}", "An")
    .header("X-Lang", "en")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.text").isEqualTo("Hello An");
~~~

**WebTestClient.bindToController(...)** thiết lập mock pipeline cho **WebFlux**. Nếu muốn dùng cú pháp WebTestClient để test một **Spring MVC** controller mà không mở server, dùng:

~~~java
WebTestClient client =
    MockMvcWebTestClient.bindToController(new BookController()).build();
~~~

Cần import **org.springframework.test.web.servlet.client.MockMvcWebTestClient**; import WebTestClient thuộc **org.springframework.test.web.reactive.server.WebTestClient**. Hai bindToController ở hai dòng trên không tương đương: một cái thiết lập WebFlux, cái còn lại thiết lập MVC. Đối với MVC controller có bean dependencies, truyền instance đã dựng hoặc dùng ApplicationContext thích hợp.

Trong Spring Boot có thể dùng **@WebFluxTest** cho WebFlux slice, hoặc **@SpringBootTest(webEnvironment = RANDOM_PORT)** kết hợp WebTestClient để chạy tích hợp với HTTP server thật. Khi test qua mock pipeline, status/headers/JSON được xác minh nhưng network, TLS, proxy/load balancer bên ngoài vẫn chưa được bao phủ.

### Kiểm tra JSON, status và header với WebTestClient

~~~java
client.get()
    .uri("/api/greetings/An")
    .header("X-Lang", "vi")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.text").isEqualTo("Xin chào An");
~~~

Có thể dùng **expectBody(Greeting.class)** để decode thành DTO, **expectBodyList(Greeting.class)** cho danh sách, hoặc **expectBody().json(...)** để so JSON có cấu trúc. Với generic phức tạp, dùng overload nhận **ParameterizedTypeReference<T>**.

Với response rỗng như HTTP 204, dùng **expectStatus().isNoContent().expectBody().isEmpty()**. Với stream SSE/NDJSON, xác minh status/header trước, sau đó lấy **FluxExchangeResult** và dùng **StepVerifier** để kiểm tra dữ liệu theo thời gian; không cố gom stream vô hạn để kiểm tra JSON body như response hữu hạn.

## 11. Tích hợp service, validation, security và error handler

Một MVC controller thường dùng service:

~~~java
@RestController
class PurchaseController {
    private final PurchaseService service;

    PurchaseController(PurchaseService service) {
        this.service = service;
    }

    @GetMapping("/api/purchases/{id}")
    Purchase find(@PathVariable long id) {
        return service.find(id);
    }
}
~~~

Khi dùng **@WebMvcTest(PurchaseController.class)**, service không tự động có mặt như trong full application context. Với Spring Boot 3.4+/Spring Framework 6.2, dùng **@MockitoBean** ở test:

~~~java
@WebMvcTest(PurchaseController.class)
class PurchaseControllerTest {
    @Autowired MockMvc mvc;

    @MockitoBean PurchaseService service;

    @Test
    void mapsIdAndSerializesResponse() throws Exception {
        given(service.find(3L)).willReturn(new Purchase(3L));

        mvc.perform(get("/api/purchases/3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(3));

        then(service).should().find(3L);
    }
}
~~~

Import **org.springframework.test.context.bean.override.mockito.MockitoBean**; **given/then** thuộc Mockito BDD (static imports). Các kiểu **PurchaseService/Purchase** ở đây là minh họa trong dự án đã khai báo sẵn; đây **không phải phần của demo chạy độc lập ở mục 8**.

Dùng test này để kiểm tra hai chiều: request HTTP có binding id đúng và controller đã gọi service với id 3; JSON response có id 3. Không nên mock **DispatcherServlet**, **HandlerMapping** hay **Jackson** khi mục tiêu là kiểm chứng Spring MVC mapping và converter.

### Validation

Khi controller dùng **@Valid @RequestBody RequestDto**, nên test:
- body hợp lệ → success (200/201);
- thiếu trường bắt buộc/constraint fail → status và error JSON theo **@ControllerAdvice** đã quy định;
- JSON sai cú pháp → 400 ở bước converter, khác lỗi Bean Validation;
- request không gửi body nhưng **@RequestBody(required=true)** → 400.

Cần thêm **spring-boot-starter-validation** nếu ứng dụng Spring Boot dựa vào Jakarta Bean Validation mà chưa có implementation. Đừng tự cho rằng chỉ có **@NotBlank** trên DTO sẽ hoạt động khi không có validation provider.

### Security

Nếu dùng Spring Security:
- **@WebMvcTest** có thể nạp security filters; anonymous request có thể trả 401/403, request POST có thể cần CSRF tùy cấu hình.
- Với test authorized route, dùng **spring-security-test** và **@WithMockUser** hoặc request post-processor thích hợp (nếu dependencies đã có).
- Cần test riêng anonymous, role thiếu và role đúng; không tắt filter chỉ để đạt status 200 trong bộ test được kỳ vọng kiểm chứng policy.
- Request header **Authorization** gửi vào MockMvc chưa đủ để giả định authentication thành công nếu ứng dụng không có filter xử lý header.

### Khi test thật sự cần end-to-end

Một test với **@SpringBootTest(webEnvironment = RANDOM_PORT)** và HTTP client nối **http://localhost:{port}** sẽ đi qua HTTP network và ứng dụng đã chạy. Hữu ích khi cần xác minh servlet container, custom filters, serialization theo cấu hình đầy đủ và các lớp tích hợp. Nó có chi phí startup và dependency state lớn hơn slice test. Đừng viết tất cả test controller thành end-to-end khi vài mệnh đề mapping/JSON có thể được kiểm nhanh, ổn định bằng MockMvc.

## 12. Lỗi thường gặp khi kiểm chứng HTTP contract

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Gọi trực tiếp method controller, test vẫn pass dù sai URL | Không đi qua HandlerMapping | Dùng MockMvc/WebTestClient gửi HTTP request mock |
| Status 200 nhưng mapping nhầm method | Chỉ assert status | Thêm MockMvc **handler().methodName(...)** khi cần |
| Assert request header bằng header().string | Nhầm request builder với response matcher | Request dùng **.header(...)**, response dùng **header().string(...)** |
| Test POST trả 415 | Quên request Content-Type hoặc consumes sai | Dùng **.contentType(APPLICATION_JSON)** với body JSON |
| Test nhận 406 | Accept không phù hợp produces | Kiểm tra **.accept(...)** và media type server hỗ trợ |
| Expected 404 nhưng thực tế 400 | Path variable không đổi được sang kiểu Java | Phân biệt lỗi binding và không có dữ liệu |
| Thiếu header X-Tenant → 400 | @RequestHeader required | Gửi header hoặc thiết kế required=false có chủ đích |
| JSONPath $.items[0] thất bại | Response thực là object khác hoặc array ở root | Xem response thật, chọn đúng JSONPath |
| Test JSON string so sánh raw bị fail vì whitespace | So sánh bytes thay vì cấu trúc JSON | Dùng JSONPath hoặc content().json |
| JSON field null và field vắng bị đánh đồng | Matcher existence sai | Phân biệt exists, hasJsonPath, doesNotHaveJsonPath |
| @WebMvcTest không tạo được context | Controller phụ thuộc service bean chưa mock | Dùng @MockitoBean hoặc test config phù hợp |
| Request POST trong app có Security trả 403 | CSRF/security filter yêu cầu chính sách | Dùng test security phù hợp, giữ đúng policy |
| Test dựa trên timestamp/random ID bị flaky | Không kiểm soát clock/seed | Inject Clock, tạo fixture ổn định |
| Test pass riêng nhưng fail theo bộ | Test phụ thuộc DB/time/static mutable state | Cô lập fixture, dọn dữ liệu, bỏ phụ thuộc thứ tự |
| MVC test không phản ánh WebFlux | Dùng MockMvc với WebFlux pipeline | Dùng WebTestClient cho WebFlux |

### Checklist trước khi chấp nhận endpoint

1. Gửi đúng method, path và verify handler/route khi mục tiêu là mapping.
2. Kiểm tra **@PathVariable**, **@RequestParam**, **@RequestHeader**, defaults và các trường hợp thiếu/sai kiểu.
3. Với POST/PUT/PATCH, gửi đúng **Content-Type**, request body và test malformed/mismatched media type.
4. Assert **status** theo contract; phân biệt success, binding errors, media negotiation errors và domain errors.
5. Assert response **headers** quan trọng như Content-Type, Location, Cache-Control, ETag hay correlation ID.
6. Assert body **JSON** bằng JSONPath hoặc structural comparison; kiểm kiểu, giá trị, nested array/object, null/missing theo schema.
7. Kiểm tra negative cases (400/404/405/415/406) và security policy nếu có.
8. Dùng slice test cho controller contract; thêm integration test khi muốn bao phủ full wiring và HTTP network.

## 13. Bài tập thực hành

**Bài 1 – Mapping và negative status.** Thêm **GET /api/books/8** trả sách khác, giữ GET /api/books/7. Viết test 200 cho id=8 và 404 cho id=99. Thêm GET /api/books/abc và xác minh 400. Giải thích sự khác nhau giữa 404 do business và route không tồn tại.

**Bài 2 – Query và header.** Thêm **@RequestParam(defaultValue="10") int limit** và một header **X-Client-Version** bắt buộc. Viết test thiếu limit dùng mặc định 10, limit=5 thành số 5, limit=oops → 400, thiếu header → 400. Khi header có giá trị, trả response header echo và assert giá trị.

**Bài 3 – JSON request và response.** Mở rộng CreateBook có title và author, trả BookView chứa nested author object. Test 201, Location, **$.author.name**; test JSON lỗi cú pháp, Content-Type text/plain, và một field thiếu sau khi thêm @Valid/@NotBlank cùng validation provider.

**Bài 4 – Array và kiểu dữ liệu.** Tạo GET /api/books trả list của hai BookView. Assert body là array, độ dài, **$[0].id** là số, **$[1].title** là String, và kiểm thứ tự nếu contract có cam kết.

**Bài 5 – WebFlux.** Viết một controller trả **Mono<BookView>**, test với **WebTestClient.bindToController**. So sánh fluent expectations và giải thích tại sao test này không nên dùng MockMvc để kiểm tra pipeline WebFlux.

## Tài liệu chính thức

- [Spring Framework 6.2 – MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html)
- [Spring Framework 6.2 – MockMvc defining expectations](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/expectations.html)
- [Spring Framework 6.2 – WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 – Testing Spring MVC applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework – @MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
