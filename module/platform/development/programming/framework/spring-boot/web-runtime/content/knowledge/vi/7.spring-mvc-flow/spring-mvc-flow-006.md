# HttpMessageConverter và xử lý nội dung yêu cầu, phản hồi trong Spring MVC

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích **HttpMessageConverter** là gì, nằm ở đâu trong luồng xử lý Spring MVC và khác gì với Converter/ConversionService.
2. Mô tả cách **@RequestBody** chuyển byte HTTP request thành đối tượng Java và cách **@ResponseBody / @RestController / ResponseEntity** chuyển giá trị Java thành response body.
3. Phân biệt **Content-Type** của thông điệp đang gửi với **Accept** của client, hiểu khi nào xảy ra HTTP 400, 406 và 415.
4. Nhận diện converter thường dùng cho JSON, String, byte[], Resource, form và XML; hiểu tác động của dependency trên classpath.
5. Viết và chạy ứng dụng Java 17+ / Spring Boot 3.3.x có endpoint nhận JSON, trả JSON, văn bản, dữ liệu nhị phân và một media type tự định nghĩa.
6. Tùy chỉnh converter, cấu hình Jackson và kiểm thử bằng MockMvc mà vẫn bảo toàn các converter mặc định.
7. Chẩn đoán các lỗi deserialize, serialize, validation, encoding và thương lượng nội dung trong ứng dụng thực tế.

**Phạm vi:** Spring MVC trên Servlet stack của **Spring Framework 6.1 / Spring Boot 3.3.x**, Java 17+. Spring WebFlux dùng hệ thống **HttpMessageReader/HttpMessageWriter** và codec tương ứng, vì vậy không áp dụng nguyên xi cấu hình HttpMessageConverter của MVC sang WebFlux.

## 1. Vấn đề cần giải quyết: HTTP chuyển byte, Java xử lý object

Một HTTP request có method, target, headers và body. Body đi qua mạng dưới dạng byte, còn controller thường muốn nhận một DTO Java. Khi trả kết quả, controller tạo DTO, String, byte[] hoặc Resource, nhưng server phải phát ra byte và Content-Type phù hợp.

Ví dụ một client gửi:

~~~http
POST /books HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":220}
~~~

Controller lại muốn tham số:

~~~java
NewBookRequest request
~~~

Sau xử lý, controller trả:

~~~java
BookResponse response
~~~

Spring MVC cần hai quá trình:

- **Đọc (deserialization):** JSON bytes từ request body -> đối tượng NewBookRequest.
- **Ghi (serialization):** đối tượng BookResponse -> JSON bytes trong response body.

**HttpMessageConverter** là chiến lược chuẩn của Spring để thực hiện hai việc này. Nó tập trung vào biểu diễn *nội dung thông điệp HTTP*, không chịu trách nhiệm kiểm tra nghiệp vụ, truy vấn database, xác thực người dùng hoặc tự tạo route.

## 2. HttpMessageConverter ở vị trí nào trong luồng Spring MVC?

Luồng đơn giản:

~~~text
HTTP client
  |
  v
Servlet container: Tomcat / Jetty / Undertow
  |
  v
Filters, Spring Security (nếu cấu hình)
  |
  v
DispatcherServlet
  |
  v
HandlerMapping tìm controller method phù hợp
  |
  v
HandlerAdapter / argument resolvers
  |
  +--- @RequestBody ---> HttpMessageConverter.read(...)
  |                        |
  |                        v
  |                  Java request DTO
  |
  v
Controller method -> service -> kết quả Java
  |
  v
Return value handlers
  |
  +--- @ResponseBody / ResponseEntity
  |          |
  |          v
  |   HttpMessageConverter.write(...)
  |          |
  |          v
  |      HTTP response body
  |
  v
Servlet container gửi response đến client
~~~

Các thành phần tiêu biểu:

- **RequestMappingHandlerMapping:** chọn handler method theo path, method, params, headers và media-type conditions.
- **RequestMappingHandlerAdapter:** gọi handler method và sử dụng các argument resolver/return-value handler.
- **RequestResponseBodyMethodProcessor:** xử lý tham số @RequestBody và các return value dùng @ResponseBody.
- **HttpEntityMethodProcessor:** xử lý HttpEntity và ResponseEntity, có sử dụng message converters cho body khi phù hợp.
- **ExceptionHandlerExceptionResolver:** cũng có thể sử dụng message converters khi @ExceptionHandler trả response body.

Đây là các vai trò chính; pipeline thực tế có thêm interceptors, advice, validation và exception resolution.

### Message conversion không chạy với mọi tham số

Không phải mọi dữ liệu đi qua HttpMessageConverter. Ví dụ:

~~~java
@GetMapping("/books/{id}")
BookResponse get(@PathVariable long id,
                 @RequestParam(defaultValue = "10") int limit) {
    // ...
}
~~~

id và limit xuất phát từ path/query parameters. Spring MVC dùng cơ chế binding/conversion thích hợp, **không đọc request body bằng JSON converter** để tạo hai giá trị đó.

Tương tự, @ModelAttribute chủ yếu dùng data binding từ request parameters tới object; file upload và form cần quy trình Servlet/multipart riêng. Chỉ khi framework cần đọc/ghi **HTTP message body** theo kiểu method argument/return value tương ứng thì HttpMessageConverter mới tham gia.

## 3. Contract của interface HttpMessageConverter<T>

Trong Spring Framework 6.1, interface nằm tại:

~~~java
org.springframework.http.converter.HttpMessageConverter<T>
~~~

Các method cốt lõi:

~~~java
boolean canRead(Class<?> clazz, MediaType mediaType);
boolean canWrite(Class<?> clazz, MediaType mediaType);

List<MediaType> getSupportedMediaTypes();

T read(Class<? extends T> clazz, HttpInputMessage inputMessage)
        throws IOException, HttpMessageNotReadableException;

void write(T value, MediaType contentType,
           HttpOutputMessage outputMessage)
        throws IOException, HttpMessageNotWritableException;
~~~

Đây là bản liệt kê chữ ký để học API, **không phải đoạn Java độc lập để biên dịch**; các lớp nằm trong package org.springframework.http và org.springframework.http.converter.

Ý nghĩa:

1. **canRead:** converter có đọc được một kiểu Java nhất định từ media type của request hay không?
2. **read:** đọc byte từ HttpInputMessage và tạo object. Ví dụ MappingJackson2HttpMessageConverter dùng Jackson ObjectMapper để deserialize JSON.
3. **canWrite:** converter có thể biểu diễn kiểu Java trả về thành media type được chọn hay không?
4. **write:** serialize object ra HttpOutputMessage. Converter thường đặt Content-Type phù hợp và ghi dữ liệu vào body.
5. **getSupportedMediaTypes:** những media type mà converter công bố hỗ trợ, có thể tùy chỉnh trong một số implementation.

**Không chỉ dựa vào Content-Type:** Spring còn phải xem **Java type**. Một converter dành cho String dù hỗ trợ text/plain chưa chắc xử lý được BookResponse; Jackson JSON converter có thể xử lý BookResponse với application/json nhưng không mặc nhiên ghi được mọi loại binary hoặc định dạng tùy biến.

### Input và output là những wrapper HTTP

- **HttpInputMessage** cho phép lấy HttpHeaders và InputStream để đọc body.
- **HttpOutputMessage** cho phép thiết lập HttpHeaders và ghi body qua OutputStream.

Lớp **AbstractHttpMessageConverter<T>** cung cấp phần lớn logic chung cho converter tự viết. Với kiểu generic phức tạp như List<BookResponse>, một số converter còn triển khai GenericHttpMessageConverter hoặc SmartHttpMessageConverter để giữ thông tin Type/ResolvableType; không tự làm mất generic type bằng cách biến mọi tham số thành Object hoặc raw List.

## 4. Hai hướng xử lý body: @RequestBody và @ResponseBody

### @RequestBody: từ request body tới Java

~~~java
@PostMapping(path = "/books", consumes = MediaType.APPLICATION_JSON_VALUE)
public BookResponse create(@RequestBody NewBookRequest request) {
    // ...
}
~~~

Diễn biến:

1. HandlerMapping xét path, HTTP method và consumes condition.
2. Resolver thấy tham số được đánh dấu @RequestBody.
3. Framework xét Content-Type thực tế, type NewBookRequest và các converter đã đăng ký.
4. Converter phù hợp đọc InputStream và tạo object.
5. Framework có thể chạy Bean Validation cho @Valid hoặc @Validated.
6. Nếu đọc/validation hợp lệ, controller method được gọi.

**@RequestBody mặc định là required=true**. Nếu body cần thiết nhưng bị thiếu, có thể phát sinh 400 Bad Request. Dùng @RequestBody(required=false) khi endpoint thực sự cho phép body vắng mặt, đồng thời xử lý null/optional rõ ràng.

Không dùng @RequestBody chỉ vì muốn lấy dữ liệu query string. Với JSON body, @RequestBody là lựa chọn thông thường; với query/path dùng @RequestParam/@PathVariable.

### @ResponseBody: từ giá trị Java tới response body

~~~java
@GetMapping("/books/1")
@ResponseBody
public BookResponse get() {
    // ...
}
~~~

Sau khi controller trả BookResponse, return value handler chọn converter có thể ghi BookResponse theo response media type rồi gọi write. Đối tượng Java **không mặc nhiên dùng toString() để làm JSON**. Với Jackson, các property được serialize theo luật Jackson.

**@RestController** tương đương tổ hợp semantics của @Controller và @ResponseBody ở mức class, nên các method thường trả trực tiếp body mà không cần gắn @ResponseBody riêng.

~~~java
@RestController
class BookController {
    @GetMapping("/books/1")
    BookResponse get() {
        // ...
    }
}
~~~

Khác với @Controller không có @ResponseBody: chuỗi return từ controller MVC cổ điển có thể là **tên view**, không phải nội dung text/plain. Khi mục đích là trả text, dùng @RestController hoặc @ResponseBody và cân nhắc produces.

### ResponseEntity còn mang status và headers

~~~java
ResponseEntity.status(HttpStatus.CREATED)
        .header("X-Source", "demo")
        .body(bookResponse);
~~~

ResponseEntity cho phép điều khiển status và headers, nhưng body vẫn thường được ghi bằng converter. Có thể dùng ResponseEntity<Void> khi chỉ cần status/headers và không có body; trường hợp đó không có object body để serialize.

Không nhầm giữa ResponseEntity và converter: ResponseEntity là **gói kết quả HTTP**; converter quyết định cách biểu diễn dữ liệu body nằm trong gói đó.

## 5. Content-Type và Accept: phân biệt trước khi debug

| Header | Chủ thể công bố | Ý nghĩa |
|---|---|---|
| Request Content-Type | Client | Kiểu nội dung **body mà client đang gửi** |
| Request Accept | Client | Những representation mà client **muốn nhận** trong response |
| Response Content-Type | Server | Kiểu nội dung **body server thực tế trả** |
| Response Vary | Server/proxy | Cho cache biết sự khác biệt của representation theo header yêu cầu khi phù hợp |

Ví dụ:

~~~http
POST /books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Java","pages":120}
~~~

- Content-Type: application/json giúp Spring lựa chọn converter để **đọc JSON request**.
- Accept: application/json giúp Spring chọn representation mà client có thể **nhận**.
- Response Content-Type: application/json cho biết body thực tế là JSON.

Một client có thể gửi JSON và muốn nhận text/plain; hai header độc lập. Điều có được hỗ trợ hay không phụ thuộc mapping, converter và kiểu dữ liệu của endpoint.

### Content-Type gắn với body của một thông điệp

Một GET request thường không có body và có thể không cần Request Content-Type. Đừng đặt Content-Type: application/json cho GET chỉ vì muốn server trả JSON; dùng **Accept: application/json** khi muốn báo sở thích response.

### Wildcard, q-value và charset

~~~http
Accept: application/json, text/plain;q=0.5
~~~

Client ưu tiên application/json hơn text/plain. Spring thực hiện nội dung negotiation dựa trên điều kiện mapping, kiểu trả về, converter có thể ghi và media types mà client chấp nhận. Nếu Accept là */*, client chấp nhận mọi media type, nhưng server vẫn phải có converter phù hợp để ghi response.

~~~http
Content-Type: application/json;charset=UTF-8
~~~

Đây vẫn là JSON, có tham số charset. Media type và charset cần được diễn giải đúng theo quy tắc HTTP và JSON; UTF-8 là lựa chọn chuẩn cho JSON trao đổi qua mạng. Không ghép chuỗi Content-Type để tự phán đoán bằng equals("application/json") vì có thể có tham số hợp lệ.

## 6. consumes, produces và kiểm tra media type tại handler

Spring MVC hỗ trợ:

~~~java
@PostMapping(
    path = "/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

- **consumes:** ràng buộc Content-Type của request body mà handler chấp nhận.
- **produces:** ràng buộc media type của response mà handler có thể tạo, được đối chiếu với Accept.
- **HttpMessageConverter:** thực hiện đọc/ghi body sau khi handler phù hợp được chọn.

Từ đó:

| Request | Điều kiện endpoint | Kết quả điển hình |
|---|---|---|
| POST Content-Type: application/json, Accept: application/json | consumes và produces đều phù hợp | Converter JSON đọc và ghi |
| POST Content-Type: text/plain | Chỉ consumes JSON | 415 Unsupported Media Type |
| POST Content-Type: application/json, Accept: text/plain | Chỉ produces JSON | 406 Not Acceptable |
| POST JSON malformed | Media type đúng nhưng parse thất bại | 400 Bad Request |
| POST JSON hợp lệ về cú pháp nhưng vi phạm @Valid | Deserialize xong, validation fail | 400 Bad Request |
| GET với Accept: application/json | Endpoint trả JSON | Chọn JSON writer nếu kiểu Java được hỗ trợ |

**406 và 415 khác nhau:** 415 liên quan đến **kiểu request body server không chấp nhận/không đọc được**; 406 liên quan đến **kiểu response client yêu cầu nhưng server không thể tạo phù hợp**. Cả hai có thể xuất hiện ngay ở bước chọn handler do consumes/produces hoặc trong quá trình chọn converter.

## 7. Các HttpMessageConverter phổ biến

Các implementation có thể hiện diện tùy Spring Framework, Spring Boot, classpath và cấu hình.

| Converter | Loại dữ liệu Java điển hình | Media type thường dùng | Ghi chú |
|---|---|---|---|
| MappingJackson2HttpMessageConverter | DTO, record, Map, List, JSON object | application/json, application/*+json | Dùng Jackson 2 khi dependency có sẵn |
| StringHttpMessageConverter | String | text/plain, các text media phù hợp | Không nên dùng String thay DTO khi muốn JSON đúng cấu trúc |
| ByteArrayHttpMessageConverter | byte[] | application/octet-stream hoặc kiểu phù hợp | Ghi/đọc byte nguyên dạng |
| ResourceHttpMessageConverter | Resource | Dữ liệu tài nguyên/file | Có logic đọc/ghi stream phù hợp resource |
| FormHttpMessageConverter | MultiValueMap | application/x-www-form-urlencoded; ghi multipart | Form submit qua Servlet MVC thường được binding qua request parameters |
| MappingJackson2XmlHttpMessageConverter | DTO/POJO | application/xml | Phụ thuộc Jackson XML và cấu hình |
| SourceHttpMessageConverter | javax.xml.transform.Source | XML media types | Xử lý XML Source khi phù hợp |
| ProtobufHttpMessageConverter | Protobuf message | application/x-protobuf | Cần thư viện Protobuf |

Tùy classpath, các converter khác cũng có thể tham gia (Gson, JSON-B, YAML, CBOR, XML,...). Đừng mặc định mọi format đều được hỗ trợ chỉ vì có Spring Boot starter-web.

### Jackson JSON và các record Java 17

Với Jackson được auto-configured trong Spring Boot 3.3, Java record đơn giản là DTO phù hợp:

~~~java
public record BookResponse(long id, String title, int pages) {}
~~~

Giá trị:

~~~java
new BookResponse(7L, "Spring MVC", 220)
~~~

thường được ghi thành JSON tương đương:

~~~json
{"id":7,"title":"Spring MVC","pages":220}
~~~

Thứ tự field, whitespace và chính sách tên field có thể thay đổi theo Jackson configuration. Test API nên kiểm tra cấu trúc JSON, không dựa vào raw string hoặc thứ tự property.

### Một String không mặc nhiên là JSON object

~~~java
@GetMapping(path = "/raw", produces = "application/json")
String raw() {
    return "{\"ok\":true}";
}
~~~

Ví dụ này rất dễ gây hiểu sai: StringHttpMessageConverter có thể được chọn để ghi String theo media type phù hợp, và giá trị String có thể được xuất dưới dạng byte nguyên văn, không có nghĩa Jackson đang serialize một DTO. Với chuỗi không chứa JSON hợp lệ, client sẽ nhận body không đúng kỳ vọng dù Content-Type là application/json.

Khi muốn JSON dạng object, hãy trả DTO, record, Map có kiểu rõ ràng hoặc ResponseEntity<DTO>:

~~~java
record Health(boolean ok) {}

@GetMapping(path = "/health", produces = MediaType.APPLICATION_JSON_VALUE)
Health health() {
    return new Health(true);
}
~~~

Đây là đoạn minh họa đặt trong @RestController đã có import phù hợp, không phải file Java tự chạy độc lập.

## 8. Form và multipart có gì khác @RequestBody JSON?

Form URL encoded và multipart thường dùng một lớp xử lý khác:

~~~http
POST /register HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=a%40example.com&name=An
~~~

Với Servlet MVC, có thể xử lý dạng này bằng @RequestParam hoặc @ModelAttribute:

~~~java
@PostMapping(
    path = "/register",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
String register(@RequestParam String email,
                @RequestParam String name) {
    return "accepted";
}
~~~

**Không** mặc nhiên đổi nó thành @RequestBody MyDto rồi kỳ vọng Jackson JSON converter đọc form. Servlet container có thể parse các request parameter trước, khiến request body không còn sẵn để một converter đọc theo cách bạn nghĩ. Spring Framework khuyến nghị dùng @RequestParam cho form data trên Servlet stack.

Với multipart/form-data:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
String upload(@RequestPart("file") MultipartFile file) {
    return file.getOriginalFilename();
}
~~~

Đây là đoạn minh họa cho controller có multipart enabled, không nên dùng tên file client gửi làm đường dẫn lưu trực tiếp. MultipartResolver/Servlet multipart handling tách các phần upload; MultipartFile được xử lý theo cơ chế multipart. Một @RequestPart chứa JSON DTO có thể dùng **HttpMessageConverter** để deserialize nội dung **riêng của part đó**, dựa trên Content-Type của part. Vì vậy không thể nói mọi multipart đều bỏ qua converters, cũng không thể nói mọi multipart đi qua JSON converter.

## 9. JSON serialize/deserialize: kiểu dữ liệu và validation

Giả sử DTO:

~~~java
public record CreateBookRequest(
        @NotBlank String title,
        @Min(1) int pages
) {}
~~~

Với tham số:

~~~java
@Valid @RequestBody CreateBookRequest request
~~~

cần cả hai bước:

1. Jackson đọc JSON thành CreateBookRequest. JSON malformed hoặc kiểu không phù hợp có thể gây HttpMessageNotReadableException.
2. Bean Validation kiểm tra constraint. Nếu validation fail trong tình huống thông thường, Spring MVC phát MethodArgumentNotValidException và phản hồi 400.

Các annotation @NotBlank, @Min thuộc Jakarta Validation; **spring-boot-starter-validation** cần có trong project. Chỉ thêm @Valid khi không có validation provider phù hợp không bảo đảm ràng buộc thực sự được thực thi.

### Phân biệt lỗi đọc body và lỗi nghiệp vụ

| Trường hợp | Tầng phát hiện | Hành vi thường gặp |
|---|---|---|
| Body không phải JSON hợp lệ | Jackson/converter | 400 |
| Body JSON thiếu required body nói chung | Resolver | 400 khi @RequestBody required |
| title trống, pages bằng 0 | Bean Validation sau deserialize | 400 |
| title hợp lệ nhưng trùng mã sản phẩm | Business service | Cần quy tắc riêng, ví dụ 409 |
| Client gửi text/plain cho JSON endpoint | Mapping/reader | 415 |
| Client chỉ Accept XML nhưng server chỉ ghi JSON | Mapping/writer | 406 |

Không gộp mọi lỗi thành 500. Khi cần format lỗi nhất quán, dùng @RestControllerAdvice với @ExceptionHandler hoặc ProblemDetail có kiểm soát. Không trả stack trace hoặc thông tin bí mật trong response.

### Jackson annotations thay đổi dữ liệu JSON

~~~java
public record UserView(
        @JsonProperty("display_name") String displayName,
        @JsonIgnore String internalToken
) {}
~~~

Đây là snippet minh họa, không phải ứng dụng độc lập. Nếu muốn response không chứa dữ liệu nhạy cảm, **thiết kế DTO public riêng** tốt hơn dựa hoàn toàn vào việc @JsonIgnore trên entity nghiệp vụ. Cẩn thận với entity có quan hệ vòng, lazy-loading, field bí mật và phiên bản API.

## 10. Ví dụ hoàn chỉnh Spring Boot 3.3.x: JSON, text, binary và custom media type

Ví dụ này gom các luồng chính vào một ứng dụng Java 17+ để bạn có thể chạy và thử với curl.

### 10.1. Tạo project và dependencies

Tạo project Spring Boot 3.3.x có Java 17 và dependency trong build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần dependencies để thêm vào một **project Gradle đã khai báo Spring Boot plugin, repositories và Java toolchain**, không phải toàn bộ build.gradle. starter-web mang Spring MVC cùng Jackson JSON; starter-validation cung cấp Jakarta Bean Validation; starter-test phục vụ MockMvc/JUnit.

### 10.2. File Java chạy trong project

Tạo **src/main/java/com/example/converters/ConverterLessonApplication.java**:

~~~java
package com.example.converters;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.AbstractHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ConverterLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterLessonApplication.class, args);
    }

    public record CreateBookRequest(
            @NotBlank String title,
            @Min(1) int pages
    ) {}

    public record BookResponse(long id, String title, int pages) {}

    public record Price(BigDecimal amount) {}

    @Bean
    static HttpMessageConverter<Price> priceTextConverter() {
        return new PriceTextConverter();
    }

    @RestController
    @RequestMapping("/books")
    static class BookController {

        private final AtomicLong ids = new AtomicLong();
        private final Map<Long, BookResponse> books =
                new ConcurrentHashMap<>();

        @PostMapping(
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<BookResponse> create(
                @Valid @RequestBody CreateBookRequest request) {
            long id = ids.incrementAndGet();

            BookResponse book =
                    new BookResponse(id, request.title(), request.pages());

            books.put(id, book);

            return ResponseEntity
                    .created(URI.create("/books/" + id))
                    .body(book);
        }

        @GetMapping(
                path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<BookResponse> get(@PathVariable long id) {
            return ResponseEntity.of(
                    Optional.ofNullable(books.get(id))
            );
        }
    }

    @RestController
    static class FormatController {

        @GetMapping(
                path = "/health-text",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String healthText() {
            return "ready";
        }

        @GetMapping(
                path = "/download-bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        byte[] binary() {
            return new byte[] {65, 66, 67};
        }

        @PostMapping(
                path = "/price",
                consumes = "text/x-price",
                produces = "text/x-price"
        )
        Price echo(@RequestBody Price price) {
            return price;
        }

        @PostMapping(
                path = "/form",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String form(@RequestParam String name) {
            return "received:" + name;
        }
    }

    static final class PriceTextConverter
            extends AbstractHttpMessageConverter<Price> {

        PriceTextConverter() {
            super(new MediaType(
                    "text", "x-price", StandardCharsets.UTF_8));
        }

        @Override
        protected boolean supports(Class<?> type) {
            return Price.class.isAssignableFrom(type);
        }

        @Override
        protected Price readInternal(
                Class<? extends Price> type,
                HttpInputMessage input) throws IOException {
            String raw = new String(
                    input.getBody().readAllBytes(),
                    StandardCharsets.UTF_8
            );

            try {
                return new Price(new BigDecimal(raw.trim()));
            } catch (NumberFormatException ex) {
                throw new HttpMessageNotReadableException(
                        "Price must contain a decimal number",
                        ex,
                        input
                );
            }
        }

        @Override
        protected void writeInternal(
                Price price,
                HttpOutputMessage output) throws IOException {
            output.getBody().write(
                    price.amount().toPlainString()
                            .getBytes(StandardCharsets.UTF_8)
            );
        }
    }
}
~~~

Điểm đáng chú ý:

- @RestController và @RequestMapping tạo các endpoint HTTP, còn MVC infrastructure tự đọc/ghi body.
- **POST /books**: MappingJackson2HttpMessageConverter đọc JSON thành CreateBookRequest. @Valid kiểm tra input; controller tạo BookResponse và ResponseEntity 201 Created cùng Location.
- **GET /books/{id}**: trả BookResponse dạng JSON nếu tìm thấy, hoặc response 404 không có body khi Optional rỗng.
- **GET /health-text**: StringHttpMessageConverter có thể ghi String "ready" với text/plain.
- **GET /download-bytes**: ByteArrayHttpMessageConverter ghi ba byte 65, 66, 67 (ASCII ABC) với application/octet-stream.
- **POST /price**: custom PriceTextConverter đọc và ghi Price bằng media type text/x-price; code minh họa cả canRead/canWrite thông qua supports() và supported media type.
- **POST /form**: dữ liệu application/x-www-form-urlencoded được Servlet MVC bind vào @RequestParam; nó khác đường JSON @RequestBody.
- Map trong bộ nhớ và AtomicLong chỉ dành cho thực nghiệm. Khi restart, dữ liệu biến mất; đây không phải persistence layer của production.

**Phạm vi compile:** Đây là một Java source file hoàn chỉnh dành cho project Spring Boot đã khai báo dependencies. Không chạy bằng javac trần vì cần classpath của Spring/Jackson/Jakarta Validation. Các endpoint được đặt trong hai nested static @RestController class, được component scan của Spring Boot tìm thấy khi package root là com.example.converters.

### 10.3. Khởi động và thử JSON

Chạy project ở thư mục gốc:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Gửi JSON trên Linux/macOS:

~~~bash
curl -i -X POST http://localhost:8080/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Spring MVC","pages":220}'
~~~

Trong PowerShell có thể dùng curl.exe để tránh alias:

~~~powershell
curl.exe -i -X POST http://localhost:8080/books -H "Content-Type: application/json" -H "Accept: application/json" --data-raw '{\"title\":\"Spring MVC\",\"pages\":220}'
~~~

**Lưu ý PowerShell:** cơ chế quote/escape của Windows PowerShell 5.1 và PowerShell 7 có khác biệt khi truyền JSON cho chương trình native. Nếu dòng một lệnh không truyền đúng body, có thể đặt JSON vào file UTF-8 rồi dùng curl.exe --data-binary "@book.json" để tránh lỗi shell quoting.

Một response điển hình cho lần POST đầu tiên:

~~~http
HTTP/1.1 201
Location: /books/1
Content-Type: application/json

{"id":1,"title":"Spring MVC","pages":220}
~~~

Không phụ thuộc tuyệt đối vào thứ tự headers, thứ tự field hay whitespace của JSON. id chỉ là 1 nếu đây là bản ghi đầu tiên trong tiến trình hiện tại.

Sau đó:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/books/1
~~~

Thông thường nhận status 200 và JSON object tương ứng. Với một id không có trong Map, endpoint trả 404.

### 10.4. Text, binary, form

Text:

~~~bash
curl -i -H 'Accept: text/plain' \
  http://localhost:8080/health-text
~~~

Response body:

~~~text
ready
~~~

Binary:

~~~bash
curl -i -H 'Accept: application/octet-stream' \
  http://localhost:8080/download-bytes
~~~

Body chứa **3 byte 0x41 0x42 0x43**, tương ứng ASCII ABC. Không dùng curl -i để kiểm tra những binary format lớn vì có thể làm terminal in ký tự không mong muốn; dùng -o file.bin và kiểm tra hash/byte count thay thế.

Form:

~~~bash
curl -i -X POST http://localhost:8080/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=An'
~~~

Response body:

~~~text
received:An
~~~

### 10.5. Custom media type text/x-price

Gửi:

~~~bash
curl -i -X POST http://localhost:8080/price \
  -H 'Content-Type: text/x-price' \
  -H 'Accept: text/x-price' \
  --data-binary '12.50'
~~~

Đầu ra:

~~~http
HTTP/1.1 200
Content-Type: text/x-price;charset=UTF-8

12.50
~~~

Content-Type có thể được hiển thị với tham số charset phù hợp theo converter. Điều chắc chắn về body trong ví dụ là **12.50**: BigDecimal được ghi bằng toPlainString(), giữ scale của input sau khi parse.

Thử gửi:

~~~bash
curl -i -X POST http://localhost:8080/price \
  -H 'Content-Type: text/x-price' \
  --data-binary 'khong-phai-so'
~~~

Converter ném HttpMessageNotReadableException khi không parse được BigDecimal, thông thường dẫn đến HTTP 400. Spring Boot có thể tạo error body khác nhau theo cấu hình và Accept; không cần cố định chuỗi JSON lỗi vào test.

### 10.6. Vì sao custom converter chỉ áp dụng cho Price?

PriceTextConverter extends AbstractHttpMessageConverter<Price>. Method supports() trả true cho Price hoặc subclass phù hợp; supported media type là text/x-price. Vì vậy converter này không nên tranh việc đọc/ghi BookResponse JSON hoặc String text/plain.

Một converter custom trong production còn cần tính đến giới hạn kích thước body, charset, bảo mật input, thông tin generic Type, streaming và exception handling. Ở đây converter cố ý tối giản, ưu tiên minh họa một media type riêng trên type rõ ràng.

## 11. Kiểm thử bốn nhóm kết quả bằng MockMvc

MockMvc cho phép gọi pipeline Spring MVC trong test mà không cần mở TCP listener thực. Thêm starter-test đã nêu ở trên và tạo file **src/test/java/com/example/converters/ConverterLessonApplicationTests.java**:

~~~java
package com.example.converters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConverterLessonApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readsJsonAndWritesCreatedJson() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Spring MVC\",\"pages\":220}"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.title").value("Spring MVC"))
            .andExpect(jsonPath("$.pages").value(220));
    }

    @Test
    void rejectsUnsupportedRequestMediaType() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsUnacceptableResponseType() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_PLAIN)
                .content("{\"title\":\"Spring MVC\",\"pages\":220}"))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void rejectsMalformedJson() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{bad-json"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void validatesAfterDeserialization() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\",\"pages\":0}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void writesPlainText() throws Exception {
        mvc.perform(get("/health-text")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void usesCustomPriceConverter() throws Exception {
        MediaType priceType = MediaType.parseMediaType("text/x-price");

        mvc.perform(post("/price")
                .contentType(priceType)
                .accept(priceType)
                .content("12.50"))
            .andExpect(status().isOk())
            .andExpect(content().string("12.50"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các test kiểm tra HTTP status, media type và body thực tế. Không phụ thuộc thứ tự thuộc tính trong JSON; test JSON path giúp tránh lỗi do Jackson có thể ghi key theo thứ tự khác nhau.

**Điểm phân biệt:** MockMvc kiểm tra lập trình framework và converter, nhưng không kiểm chứng TCP, TLS hay embedded server bind port. Muốn kiểm tra một server thật, dùng @SpringBootTest(webEnvironment=RANDOM_PORT) cùng HTTP client phù hợp.

## 12. Cách Spring chọn converter khi có nhiều lựa chọn

Giả sử một danh sách converter đã được đăng ký. Khi đọc @RequestBody, Spring thử chọn converter có thể xử lý Java type của tham số cùng Content-Type thực tế; converter đầu tiên phù hợp theo thứ tự cấu hình có thể được chọn.

Khi ghi @ResponseBody, Spring cần xác định response media type theo Accept, produces, loại giá trị và các media types có thể ghi. Sau đó nó chọn converter thích hợp trong danh sách.

Một bảng quy tắc khái quát:

~~~text
Request body:
  Java target type + request Content-Type
      -> tìm converter canRead(...)
      -> read(...)
      -> Java object / lỗi đọc

Response body:
  Java return type + Accept + produces + supported media types
      -> xác định response media type
      -> tìm converter canWrite(...)
      -> write(...)
      -> HTTP body / lỗi ghi
~~~

**Thứ tự converter có thể quan trọng** nếu nhiều converter cùng nhận một kiểu dữ liệu/media type. Ví dụ custom JSON converter hỗ trợ rất rộng và được đặt trước Jackson có thể thay đổi toàn bộ cách serialize JSON. Vì vậy custom converter nên có **supports() và supported media types hẹp**, đồng thời test cả các endpoint không liên quan.

### Generic type và List<T>

~~~java
@GetMapping("/book-list")
List<BookResponse> list() {
    // ...
}
~~~

Với JSON, Jackson converter có thể giữ type thông qua cơ chế generic converter/Type được truyền qua MVC pipeline, không chỉ nhìn thấy raw class List.class. Điều này giúp xử lý cấu trúc dữ liệu phức tạp, nested object và generic collections đúng hơn. Không tự viết converter cho raw Object chỉ vì muốn “hỗ trợ tất cả”.

## 13. Cấu hình và mở rộng trong Spring Boot

Spring Boot 3.3 tự cấu hình các converter mặc định dựa trên dependency, bao gồm Jackson JSON nếu starter-web có Jackson. Trong nhiều trường hợp **không cần khai báo bean converter**.

### Cách 1: Cấu hình Jackson qua properties

Ví dụ:

~~~yaml
spring:
  jackson:
    serialization:
      indent-output: true
~~~

Property này yêu cầu Jackson định dạng JSON đẹp hơn. Nó tác động đến phần serialize JSON được Jackson mapper quản lý, **không** làm thay đổi ByteArrayHttpMessageConverter hay StringHttpMessageConverter.

Khi API có nhiều client, không tự thay đổi kiểu dữ liệu JSON công khai chỉ để phục vụ log/debug. Indentation chỉ là ví dụ cấu hình không thay đổi ý nghĩa dữ liệu.

### Cách 2: Cấu hình ObjectMapper qua Boot customizer

Thêm một @Configuration trong ứng dụng Spring MVC:

~~~java
import com.fasterxml.jackson.databind.SerializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JsonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer prettyJson() {
        return builder ->
                builder.featuresToEnable(
                        SerializationFeature.INDENT_OUTPUT);
    }
}
~~~

Đây là **một class cấu hình bổ sung**, không phải chương trình Java tự chạy riêng. Nên chọn cấu hình YAML hoặc code theo nhu cầu; không cần cố ý bật cùng một setting ở nhiều nơi.

Khi muốn xử lý kiểu Java đặc thù, có thể dùng module/serializer/deserializer Jackson được đăng ký qua cấu hình mapper của Boot. Chỉ thay cả converter khi có nhu cầu thật và có test tương thích.

### Cách 3: Thêm một HttpMessageConverter bean

Trong ví dụ đầy đủ phía trên:

~~~java
@Bean
static HttpMessageConverter<Price> priceTextConverter() {
    return new PriceTextConverter();
}
~~~

Spring Boot phát hiện bean kiểu HttpMessageConverter và đưa nó vào danh sách phù hợp, theo cơ chế auto-configuration của MVC. Cách này hữu ích khi muốn bổ sung type/media format riêng.

### Cách 4: WebMvcConfigurer.extendMessageConverters

Khi phải chỉnh danh sách đã tạo, có thể dùng:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class ConverterInspectionConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Quan sát hoặc sắp xếp converter thật sự cần thay đổi.
        // Không xóa converter mặc định khi chưa xác định tác động.
    }
}
~~~

Đoạn này là cấu hình minh họa extension point. Phương thức **extendMessageConverters** chạy trên danh sách đã được thiết lập, phù hợp để điều chỉnh có kiểm soát.

**Chú ý:** Trong Spring MVC thuần, override configureMessageConverters và thêm converter vào list có thể ngăn registration mặc định. Spring Boot bổ sung cơ chế auto-configuration riêng và HttpMessageConverters; tốt nhất dùng cơ chế của Boot hoặc extendMessageConverters để tránh mất JSON, String, byte[] hoặc các converter khác.

### @EnableWebMvc là quyết định lớn

Nếu chỉ muốn thêm converter, **không** gắn @EnableWebMvc theo thói quen. Trong Spring Boot, @EnableWebMvc làm ứng dụng chuyển sang cấu hình MVC do bạn tự kiểm soát sâu hơn và có thể làm mất nhiều tiện ích auto-configuration. Hãy cân nhắc tác động đến content negotiation, static resources, message converters và các thiết lập MVC khác trước khi bật.

## 14. So sánh HttpMessageConverter với ConversionService và Jackson

| Thành phần | Hoạt động ở đâu | Ví dụ | Mục tiêu |
|---|---|---|---|
| HttpMessageConverter | Đọc/ghi toàn bộ HTTP body | JSON bytes -> BookRequest | Biểu diễn body và media type |
| ConversionService / Converter<S,T> | Chuyển giữa Java types khi binding | Query "42" -> Integer 42 | Java object -> Java object |
| PropertyEditor/Formatter | Binding và format tham số | Query date string -> LocalDate | Chuyển/định dạng thuộc tính |
| Jackson ObjectMapper | Serialize/deserialize JSON ở thư viện | Java record -> JSON | Cơ chế JSON cụ thể |
| RequestBodyAdvice | Can thiệp quanh quá trình đọc body | Kiểm tra/sửa dữ liệu trước hoặc sau converter | Logic xuyên suốt cho body đọc |
| ResponseBodyAdvice | Can thiệp trước khi body được ghi | Bọc response theo API envelope | Logic xuyên suốt cho body ghi |
| Filter/Interceptor | Trước/sau request handling | Tracing, auth, metric | Cơ chế HTTP request pipeline |

Một MappingJackson2HttpMessageConverter **sử dụng Jackson**; Jackson không thay thế cả cơ chế MVC lựa chọn converter. Một Converter<String, Long> của ConversionService không tự đọc stream JSON. Các khái niệm này thường có tên “converter” nhưng giải quyết vấn đề khác nhau.

### RequestBodyAdvice và ResponseBodyAdvice

Nếu cần can thiệp chung quanh body, Spring MVC có các extension points:

- RequestBodyAdvice: can thiệp trước/sau khi đọc request body qua HttpMessageConverter.
- ResponseBodyAdvice: can thiệp vào object return trước khi converter ghi body.

Đây là cơ chế mạnh, nhưng việc bọc response tùy tiện có thể phá ResponseEntity<byte[]>, Resource, String, ProblemDetail, file download hoặc streaming. Hãy kiểm tra supports() kỹ và test từng media type. Không dùng advice chỉ để làm nhiệm vụ vốn thuộc service/validation.

## 15. Khi nào converter không tham gia?

Cần biết những ngoại lệ để không debug nhầm:

- **@RequestParam/@PathVariable:** binding/conversion của tham số, không phải đọc raw HTTP body bằng JSON converter.
- **@ModelAttribute:** object được bind từ request parameters, khác @RequestBody JSON.
- **View rendering:** Controller trả tên view và ViewResolver render template; đây không phải @ResponseBody object được serialize như REST.
- **MultipartFile:** file part được xử lý qua multipart infrastructure; @RequestPart JSON DTO vẫn có thể dùng converter.
- **StreamingResponseBody:** trả dữ liệu theo stream qua callback được Spring MVC quản lý, không đơn thuần serialize DTO qua converter thông thường.
- **Response không có body:** 204 No Content, HEAD response, hoặc ResponseEntity<Void> không cần ghi object body.
- **Static resources:** ResourceHttpRequestHandler và bộ xử lý resource có cơ chế riêng.
- **WebFlux:** dùng HTTP codecs/readers/writers; có thể có Jackson nhưng không dùng cùng MVC HttpMessageConverter pipeline.

Nếu gặp một loại return value mà converter không bao giờ được gọi, trước hết xác định controller method có dùng @ResponseBody/@RestController hoặc ResponseEntity hay đang đi qua cơ chế view, streaming, multipart hay handler riêng.

## 16. Các lỗi và cách chẩn đoán

### 400 Bad Request

Nguyên nhân hay gặp:

- JSON không parse được, field type sai, cú pháp thiếu dấu nháy/dấu phẩy.
- Body bắt buộc nhưng trống.
- Bean Validation thất bại sau deserialize.
- Custom converter ném HttpMessageNotReadableException.

Cách xử lý:

1. Log và kiểm tra Content-Type thực tế, body theo môi trường test an toàn, DTO target.
2. Xác định nguyên nhân nằm ở parser hay validation.
3. Trả error response có cấu trúc, không để lộ stack trace.
4. Viết test cho JSON malformed, DTO invalid và body thiếu.

### 415 Unsupported Media Type

Nguyên nhân:

- Client gửi Content-Type không khớp consumes của endpoint.
- Không có converter có thể đọc target type từ media type đã gửi.
- Custom converter chỉ supports một type nhưng controller nhận kiểu khác.

Ví dụ endpoint chỉ nhận application/json nhưng client gửi text/plain. Cách sửa tốt nhất là gửi đúng Content-Type và JSON body hoặc sửa contract endpoint có chủ đích; không thêm converter hỗ trợ mọi media type một cách thiếu kiểm soát.

### 406 Not Acceptable

Nguyên nhân:

- Request Accept không tương thích với produces.
- Server không có converter có thể ghi object theo media type yêu cầu.

Ví dụ client Accept: application/xml nhưng server chỉ có khả năng/handler sản xuất JSON. Đừng tự thêm XML dependency để chữa mọi trường hợp 406; trước tiên xác định API có được thiết kế hỗ trợ XML hay không.

### 500 và lỗi ghi response

Có thể phát sinh khi converter không serialize được object, gặp circular reference, lỗi Jackson getter hoặc stream đã bị ghi một phần. Một số lỗi ghi sau khi response đã commit không thể sửa thành body lỗi JSON đầy đủ. Hãy thiết kế DTO độc lập, tránh circular reference và dùng logging correlation id thích hợp.

### Văn bản bị lỗi dấu tiếng Việt

Kiểm tra:

- Charset thực tế của response và Content-Type.
- Bytes được tạo bởi converter hoặc custom code.
- Mã hóa source file và cách đọc input.
- Proxy có sửa header hoặc nén/chuyển body hay không.
- Client hiển thị sai charset.

Với custom converter, dùng StandardCharsets.UTF_8 rõ ràng. Với Jackson JSON hiện đại, JSON UTF-8 là cách trao đổi thông thường. Đừng tự thêm thao tác encode/decode một lần nữa vào String đã được Spring xử lý.

### String trả về nhưng không phải JSON như mong đợi

Trường hợp hay gặp: controller trả String chứa JSON text và đặt produces=application/json, nên client thấy raw text hoặc JSON không đúng cấu trúc. Dùng object/record/Map và để Jackson serialize; nếu chủ đích là raw text, trả text/plain.

### Converter đúng nhưng không được chọn

Xem:

1. Java target/return type thực tế; có bị trả thành Object, String hoặc một generic wrapper không?
2. Content-Type request và Accept response.
3. consumes/produces trên mapping.
4. Danh sách converter và thứ tự đăng ký.
5. Một bean @EnableWebMvc hoặc WebMvcConfigurer tùy chỉnh có thay cấu hình mặc định không?
6. Dependency Jackson/XML/Gson/Protobuf có hiện diện không?
7. Custom supports() và supported media types có hẹp/quá rộng không?

## 17. Quan sát converter thật sự được Spring MVC đăng ký

Trong ứng dụng Spring Boot MVC, có thể tiêm RequestMappingHandlerAdapter sau khi context đã tạo và liệt kê converter:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;

@Configuration(proxyBeanMethods = false)
class ConverterDiagnostics {

    @Bean
    ApplicationRunner printMessageConverters(
            RequestMappingHandlerAdapter adapter) {
        return args -> adapter.getMessageConverters().forEach(
                converter -> System.out.println(
                        converter.getClass().getSimpleName()
                )
        );
    }
}
~~~

Đây là class cấu hình bổ sung trong **Spring MVC application**, không phải chương trình standalone. Tên và thứ tự danh sách phụ thuộc dependencies cùng cấu hình runtime, nên không đoán cố định một danh sách stdout cho mọi ứng dụng.

Trong debug, có thể bật log phù hợp tạm thời:

~~~properties
logging.level.org.springframework.web.servlet.mvc.method.annotation=DEBUG
logging.level.org.springframework.http.converter=DEBUG
~~~

Không phải converter nào cũng phát log chi tiết ở đúng hai package này. Nếu cần trace sâu, xem log thật và debugger. Không để DEBUG/TRACE body nhạy cảm hoặc thông tin người dùng chạy liên tục ở production.

## 18. Bảo mật và thiết kế API quanh message conversion

### Không serialize trực tiếp persistence entity

Entity có thể chứa password hash, access token, quan hệ lazy-loading hoặc thông tin nội bộ. Jackson có thể serialize nhiều field hơn API contract mong muốn; DTO public giúp giới hạn rõ dữ liệu response.

### Không deserialize vào type quá chung khi không cần

Nếu controller nhận Object/Map<String,Object> cho một endpoint có schema cố định, validation và type safety yếu hơn so với DTO có constraint. Chọn DTO rõ ràng và xử lý unknown properties theo chính sách API.

### Giới hạn body và độ sâu JSON

HttpMessageConverter chuyển dữ liệu, **không tự thay thế chính sách giới hạn request size, content length, JSON nesting depth hoặc resource limits**. Với endpoint nhận dữ liệu lớn, cấu hình limit phù hợp ở proxy, server và parser; đánh giá rủi ro bộ nhớ. Custom converter ví dụ dùng readAllBytes() chỉ dành cho nội dung văn bản nhỏ, không nên áp dụng nguyên xi cho upload lớn.

### Content-Type không phải chứng cứ dữ liệu an toàn

Client có thể khai báo application/json nhưng gửi dữ liệu hỏng hoặc độc hại. Parser, validation và service vẫn phải kiểm tra input. Ngay cả khi deserialize thành công, những ràng buộc nghiệp vụ như quyền truy cập, trạng thái giao dịch và giới hạn số lượng cần được kiểm tra riêng.

### ResponseContentType và cache

Khi API có nhiều representation (JSON, XML, text), có thể cần Vary: Accept, ETag và chiến lược cache phù hợp. Không tự gắn một Content-Type không đúng với bytes đang trả. Client, browser và cache đều dựa vào metadata này để xử lý nội dung.

## 19. Bài tập tự đánh giá

**Tình huống A:** POST /books có consumes=application/json. Client gửi JSON text hợp lệ nhưng Content-Type=text/plain. Tại sao có thể nhận 415?

**Đáp án:** Server dựa trên media type **khai báo trong header**, cùng điều kiện mapping/converter, không đoán body phải là JSON bằng cách nhìn nội dung. Gửi Content-Type: application/json.

**Tình huống B:** Client gửi Accept=text/plain cho endpoint chỉ produces=application/json. Body gửi vào là JSON đúng. Lỗi nào phù hợp?

**Đáp án:** 406 Not Acceptable, vì server không thể cung cấp representation mà client yêu cầu, dù request body đã đúng Content-Type.

**Tình huống C:** DTO parse JSON thành công nhưng @Valid phát hiện title trống. Converter có bị lỗi parse không?

**Đáp án:** Không. Deserialize thành công; Bean Validation thất bại ở bước tiếp theo và thông thường trả 400.

**Tình huống D:** GET method trả String "hello" trong @Controller không gắn @ResponseBody. Có chắc nhận text/plain?

**Đáp án:** Không. Trong MVC controller kiểu view, String có thể được xem là view name. Dùng @RestController/@ResponseBody khi muốn trả String body.

**Tình huống E:** API trả BookResponse nhưng dev muốn nội dung application/pdf. Chỉ sửa produces=application/pdf đã đủ chưa?

**Đáp án:** Chưa. Cần representation thực sự cho PDF, converter/streaming mechanism phù hợp và Content-Type đúng. Gắn media type vào mapping không tự biến object thành PDF bytes.

**Tình huống F:** Tại sao không dùng ConversionService.convert(String, BookResponse.class) thay Jackson để đọc JSON body?

**Đáp án:** ConversionService dành cho Java type conversion/binding; HTTP JSON body cần parser và converter hỗ trợ media type, stream và schema tương ứng.

**Tình huống G:** Một custom converter canWrite(Object.class, */*) được đăng ký trước Jackson và đột nhiên mọi JSON response đổi dạng. Nguyên nhân?

**Đáp án:** Converter hỗ trợ quá rộng và thứ tự lựa chọn khiến nó chiếm công việc của Jackson. Giới hạn supports() vào type/format thực sự cần và kiểm thử endpoint khác.

**Tình huống H:** Có thể dùng @RequestPart cho JSON metadata trong một multipart request không?

**Đáp án:** Có. Multipart infrastructure tách part, và Spring có thể dùng HttpMessageConverter cho phần metadata JSON theo Content-Type của part; MultipartFile là cơ chế xử lý file tương ứng.

## 20. Checklist ứng dụng

- [ ] Phân biệt @RequestBody/@ResponseBody với @RequestParam/@ModelAttribute.
- [ ] Với REST API, dùng DTO/record rõ type và validation constraints phù hợp.
- [ ] Khai báo consumes/produces khi contract media type cần rõ ràng.
- [ ] Gửi Content-Type đúng cho request body; dùng Accept để yêu cầu response representation.
- [ ] Hiểu 400 là lỗi đọc/validation, 415 là input media type, 406 là response media type.
- [ ] Để Jackson JSON converter xử lý DTO, tránh tự ghép chuỗi JSON bằng tay.
- [ ] Nếu thêm converter, giới hạn Java type và media type; giữ converter mặc định.
- [ ] Không bật @EnableWebMvc chỉ để sửa một chuyển đổi nhỏ trong Boot.
- [ ] Tách form/multipart/streaming khỏi pipeline JSON body khi thiết kế endpoint.
- [ ] Kiểm thử JSON, String, binary và ít nhất các lỗi 400, 406, 415.
- [ ] Giới hạn request body, giữ thông tin nhạy cảm ngoài response.
- [ ] Dùng log/MockMvc để xác minh status, headers, body và converter được chọn.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Servlet Web Applications, mục HttpMessageConverters](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Framework 6.1 — HttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/converter/HttpMessageConverter.html)
- [Spring Framework 6.1 — WebMvcConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework — @RequestBody và @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
