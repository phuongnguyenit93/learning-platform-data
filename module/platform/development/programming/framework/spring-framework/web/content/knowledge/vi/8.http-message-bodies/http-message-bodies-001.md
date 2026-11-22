# HttpMessageConverter và quá trình đọc/ghi request–response body trong Spring MVC

## 1. Mục tiêu và phạm vi

`HttpMessageConverter<T>` là cơ chế Spring Framework dùng để **đọc byte từ HTTP request body thành dữ liệu Java** và **ghi dữ liệu Java thành HTTP response body**. Đây là thành phần nền tảng phía sau `@RequestBody`, `@ResponseBody`, `@RestController`, `HttpEntity` và `ResponseEntity` trong **Spring Web MVC**.

Sau bài học, bạn có thể:

1. Trình bày điểm bắt đầu và kết thúc của quá trình đọc/ghi body trong một request MVC.
2. Giải thích Spring chọn converter dựa trên kiểu Java, `Content-Type`, `Accept` và các điều kiện của handler.
3. Phân biệt converter JSON, chuỗi, byte array, form data và tài nguyên nhị phân.
4. Xây dựng controller nhận JSON/text/binary rồi tạo response có status, headers và body đúng media type.
5. Phân biệt lỗi chọn converter với lỗi deserialize, validation và lỗi ghi response; xác định thời điểm cần tạo converter tùy biến.
6. Tránh các nhầm lẫn giữa `@RequestBody`, `@ModelAttribute`, `@RequestPart`, `@ResponseBody` và render view.

Ví dụ dùng **Java 17, Spring Boot 3.3.5 (Spring Framework 6.1.x)** để khởi động một ứng dụng Spring MVC. Spring Boot cung cấp cấu hình mặc định và thư viện JSON thông dụng; hành vi được giải thích thuộc Spring MVC. Những phiên bản Spring Framework mới hơn có thể có converter và API cấu hình khác, vì vậy phần API cụ thể bên dưới được gắn với thế hệ 6.1.

## 2. Body của HTTP là gì, và converter làm gì?

Request ví dụ:

```http
POST /api/messages HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Request-Id: req-42

{"message":"Hi","copies":2}
```

- `Content-Type` mô tả **kiểu biểu diễn request body được gửi đến server**.
- `Accept` mô tả **kiểu biểu diễn response body mà client có thể nhận**.
- Hai header này là thông tin về **media type**, không phải cấu trúc class Java.
- JSON trong request là byte/chuỗi được mã hóa; converter phải chuyển nó thành object mà controller khai báo.

Nếu method của controller nhận `EchoInput` và trả `EchoOutput`, đường đi thường là:

```text
Request bytes (JSON)
        |
        v
Servlet container / HttpServletRequest
        |
        v
DispatcherServlet + HandlerMapping chọn controller
        |
        v
Argument resolver gặp @RequestBody EchoInput
        |
        v
HttpMessageConverter đọc JSON -> EchoInput
        |
        v
(Bean Validation nếu có @Valid) -> controller
        |
        v
Controller trả EchoOutput hoặc ResponseEntity<EchoOutput>
        |
        v
Return-value handler + HttpMessageConverter ghi EchoOutput -> JSON bytes
        |
        v
HTTP response (status + headers + body)
```

Ví dụ phản hồi thành công:

```http
HTTP/1.1 201
Content-Type: application/json
X-Converted-By: spring-mvc

{"echoed":"HiHi","utf16Units":4}
```

Spring không tự biến mọi object thành JSON trong mọi trường hợp. Việc đọc/ghi thành công phụ thuộc vào việc có **converter thích hợp được đăng ký**, media type khớp và object có thể serialize/deserialize. Các ví dụ HTTP ở bài học chỉ biểu diễn những headers quan trọng; headers hệ thống có thể khác theo container và cấu hình.

### HttpMessageConverter không làm tất cả việc xử lý HTTP

`HttpMessageConverter` không trực tiếp quyết định endpoint nào được gọi, không thay thế authorization hay business logic và không tự đảm bảo Bean Validation. Phân trách nhiệm cơ bản:

| Thành phần | Trách nhiệm |
| --- | --- |
| `DispatcherServlet` / `HandlerMapping` | Chọn handler theo URL, HTTP method, `consumes`, `produces`, điều kiện khác |
| Argument resolver | Tạo tham số Java cho method, khi cần thì yêu cầu converter đọc body |
| `HttpMessageConverter` | Chuyển đổi giữa HTTP body và kiểu Java được hỗ trợ |
| JSON mapper (ví dụ Jackson) | Thực hiện chi tiết serialize/deserialize JSON cho JSON converter |
| Bean Validation | Kiểm tra constraint như `@NotBlank`, `@Min` sau khi bind |
| Return-value handler | Chọn cách xử lý giá trị trả về: response body, view, async response… |
| `ResponseEntity` | Đóng gói status + headers + body cho response |

## 3. Giao diện HttpMessageConverter<T>

Trong Spring Framework 6.1, giao diện `org.springframework.http.converter.HttpMessageConverter<T>` mô tả hợp đồng đọc/ghi. Các thao tác tiêu biểu là:

```java
boolean canRead(Class<?> clazz, MediaType mediaType);
boolean canWrite(Class<?> clazz, MediaType mediaType);
List<MediaType> getSupportedMediaTypes();
T read(Class<? extends T> clazz, HttpInputMessage inputMessage)
        throws IOException, HttpMessageNotReadableException;
void write(T value, MediaType contentType,
           HttpOutputMessage outputMessage)
        throws IOException, HttpMessageNotWritableException;
```

Đây là **hình dạng API rút gọn để giải thích**, chưa phải một interface Java hoàn chỉnh có đủ imports/annotations/generic overloads.

Ý nghĩa:

- `canRead`: converter có khả năng đọc nội dung theo **kiểu Java đích** và media type của request không?
- `read`: đọc bytes từ `HttpInputMessage.getBody()` và tạo giá trị Java. Nếu nội dung sai cấu trúc/không chuyển đổi được, converter có thể ném `HttpMessageNotReadableException`.
- `canWrite`: converter có khả năng xuất object theo media type mong muốn không?
- `write`: serialize object và ghi bytes qua `HttpOutputMessage.getBody()`, đồng thời thiết lập thông tin headers cần thiết.
- `getSupportedMediaTypes`: tập media types mà converter khai báo hỗ trợ; các converter còn có khả năng xét generic types thông qua những giao diện mở rộng.

Ví dụ `List<EchoInput>` đòi hỏi giữ thông tin generic để Jackson biết kiểu phần tử. Spring MVC có hỗ trợ những converter/giao diện chuyên biệt như `GenericHttpMessageConverter`, chứ không chỉ suy từ `List.class` rồi đoán.

Converter được Spring MVC giữ trong hạ tầng `RequestMappingHandlerAdapter` và các thành phần xử lý response liên quan. Ở client như `RestTemplate` hoặc `RestClient` cũng có khái niệm message converters, nhưng bài này tập trung phía server MVC.

## 4. Spring MVC đọc request body như thế nào?

Khi request khớp mapping sau:

```java
@PostMapping(path = "/messages",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> create(@RequestBody EchoInput input) {
    // ...
}
```

Luồng chính:

1. Handler mapping kiểm tra phương thức, URL và ràng buộc `consumes`. `consumes="application/json"` nói rằng endpoint nhận JSON body.
2. Argument resolver xác định tham số `@RequestBody EchoInput` cần đọc body.
3. MVC duyệt các message converters đã đăng ký, tìm converter có thể đọc **`EchoInput` từ `application/json`**; trong cấu hình Boot 3.3.5 có Jackson 2, đó thường là `MappingJackson2HttpMessageConverter`.
4. Converter lấy body dạng bytes từ request; JSON mapper tạo `EchoInput` và chuyển các trường tương ứng theo kiểu Java.
5. Nếu có `@Valid` và validator phù hợp, Spring kiểm tra constraint; controller chỉ chạy sau bước xử lý tham số thành công.
6. Nếu body bắt buộc nhưng không đọc được, method có thể chưa được gọi và MVC chuyển lỗi thành HTTP response.

`@RequestBody` mặc định có `required = true`; bạn có thể đặt `@RequestBody(required = false)` nếu nghiệp vụ cho phép không có body, rồi **phải xử lý giá trị null**. Đừng nhầm request body thiếu với JSON object rỗng `{}`: object rỗng vẫn là nội dung hợp lệ về cú pháp nhưng có thể thiếu fields hoặc vi phạm validation.

### @RequestBody, HttpEntity và những cách nhận dữ liệu khác

```java
public void json(@RequestBody EchoInput input) { /* ... */ }
public void both(HttpEntity<EchoInput> request) { /* ... */ }
public void header(@RequestHeader("X-Request-Id") String id,
                   @RequestBody EchoInput input) { /* ... */ }
```

Ba method trên chỉ là **chữ ký minh họa**, cần annotations mapping và đặt trong một controller để hoạt động. `HttpEntity<EchoInput>` chứa cả `getBody()` và `getHeaders()`, và được argument resolver chuyển đổi body thông qua converter; không cần đặt `@RequestBody` lên `HttpEntity`. Nếu chỉ cần một header, `@RequestHeader` cùng `@RequestBody` thường rõ ràng hơn.

Cần tách biệt:

- `@RequestParam`, `@ModelAttribute`: thông thường dùng binding tham số query/form thông qua `WebDataBinder`, **không phải** con đường deserialize JSON chuẩn của `@RequestBody`.
- `@RequestPart`: dùng cho một part của multipart request, có thể chuyển part JSON bằng converter thích hợp.
- `HttpServletRequest.getInputStream()`: cho phép thao tác trực tiếp stream body khi cần raw bytes; tự đọc stream có thể khiến framework không còn dữ liệu để đọc lại.
- `MultipartFile`: dùng cơ chế multipart và lưu trữ tệp upload, không nên thay bằng một `@RequestBody byte[]` khổng lồ cho mọi use case.

Đặc biệt, body của `application/x-www-form-urlencoded` có thể đã bị Servlet container parse khi truy cập request parameters. Với HTML form thường nên dùng `@RequestParam` hoặc `@ModelAttribute`, không dựa vào việc đọc lại cùng body qua `@RequestBody`.

## 5. Spring MVC ghi response body như thế nào?

Một controller có thể trả object Java:

```java
@RestController
public class ProductController {
    @GetMapping(path = "/api/products/7",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductDto findOne() {
        return new ProductDto(7L, "Book");
    }

    public record ProductDto(long id, String name) {}
}
```

Vì `@RestController` tương đương `@Controller` cộng semantics `@ResponseBody` trên các handler methods, giá trị `ProductDto` được serialize thành HTTP body. Nếu Jackson converter phù hợp được đăng ký, response tương ứng có thể là:

```http
HTTP/1.1 200
Content-Type: application/json

{"id":7,"name":"Book"}
```

Với `@Controller` thông thường, một giá trị trả về kiểu `String` **có thể được hiểu là tên view để render**, tùy chữ ký/annotation. Khi muốn trả text hoặc JSON body, dùng `@ResponseBody`, `@RestController` hoặc `ResponseEntity` phù hợp.

`ResponseEntity<T>` bổ sung status và headers bên cạnh body:

```java
return ResponseEntity.status(HttpStatus.CREATED)
        .header("X-Created-By", "mvc")
        .body(new ProductDto(7L, "Book"));
```

Return-value handler lấy object `ProductDto`, xác định media type có thể viết (xét `produces`, client `Accept` và converter), chọn converter, sau đó viết bytes. `ResponseEntity` không bỏ qua converter: **body của nó vẫn phải được chuyển thành định dạng có thể gửi**.

Khi trả `ResponseEntity<Void>` hoặc status `204 No Content`, thông thường không có body cần serialize. Đừng hứa rằng một object vẫn sẽ được ghi xuống body của status cấm body. Với `ResponseEntity<Resource>`, MVC có converter và hành vi hỗ trợ tài nguyên; vấn đề file download, range requests và streaming cần xem xét cấu hình/kiểu Resource cụ thể.

### @ResponseBody không đồng nghĩa với “mặc định JSON”

Nếu trả `String` từ `@RestController`, `StringHttpMessageConverter` thường xử lý chuỗi thành text. Nếu trả object, JSON converter có thể xử lý khi JSON phù hợp với media type mong muốn. Khi dùng `produces = "application/json"`, đảm bảo nội dung do converter ghi thực sự là JSON hợp lệ; không tự nối chuỗi trông giống JSON rồi khai báo bừa Content-Type.

## 6. Các converter thường gặp

Trong Spring Framework 6.1, những loại quan trọng gồm:

| Converter | Kiểu Java tiêu biểu | Nội dung có thể xử lý |
| --- | --- | --- |
| `MappingJackson2HttpMessageConverter` | DTO, record, `Map`, `List<Dto>` | JSON, thường `application/json` và `application/*+json`, khi có Jackson 2 |
| `StringHttpMessageConverter` | `String` | Text, thường `text/plain` và các text media types |
| `ByteArrayHttpMessageConverter` | `byte[]` | Raw bytes; converter có thể hỗ trợ `*/*` |
| `ResourceHttpMessageConverter` | `Resource` | Dữ liệu tài nguyên/tệp |
| `FormHttpMessageConverter` | `MultiValueMap` | Đọc/ghi `application/x-www-form-urlencoded`; hỗ trợ **ghi** multipart |
| `MappingJackson2XmlHttpMessageConverter` | DTO/record nếu mapper hỗ trợ | XML khi thêm dependency Jackson XML |
| `SourceHttpMessageConverter` | XML `Source` | Các XML `Source` được hỗ trợ |

Bảng phản ánh hệ Spring Framework 6.x/Jackson 2; không nên bê nguyên tên converter giữa các major versions mà không kiểm tra tài liệu phiên bản. Việc hỗ trợ XML, Protobuf hay thư viện thứ ba phụ thuộc classpath, cấu hình và độ ưu tiên. `FormHttpMessageConverter` **không phải** cơ chế duy nhất nhận multipart upload: Spring MVC còn có multipart resolution và các argument resolvers như `@RequestPart` / `MultipartFile`.

### Vì sao String và byte[] có thể gây nhầm?

`StringHttpMessageConverter` và `ByteArrayHttpMessageConverter` có phạm vi media type tương đối rộng. Vì thế:

- Với Java return type `String`, converter text có thể được chọn trước converter JSON tùy cấu hình/thứ tự; body có thể là các ký tự nguyên văn. Đừng coi `"hello"` là JSON string hợp lệ chỉ vì response được dán header JSON.
- Với `byte[]`, dữ liệu trả về là bytes thực; nếu đó là PDF, hình ảnh hoặc binary, hãy khai báo `Content-Type` phù hợp (ví dụ `application/pdf` / `application/octet-stream`), và cân nhắc `Content-Disposition` khi tải tệp.
- Với JSON DTO, giữ response type là record/DTO giúp Jackson đảm nhiệm escape ký tự, null policy và biểu diễn JSON đúng quy tắc.

## 7. Content-Type, Accept, consumes và produces

Bốn tên này thường bị trộn lẫn:

| Tên | Bên đặt | Ý nghĩa chính |
| --- | --- | --- |
| Request `Content-Type` | Client | Body request đang được gửi theo kiểu gì |
| Request `Accept` | Client | Client muốn/cho phép nhận response media type nào |
| Mapping `consumes` | Server/controller | Endpoint được chọn cho kiểu request body nào |
| Mapping `produces` | Server/controller | Endpoint có thể tạo response theo media type nào |

Ví dụ:

```java
@PostMapping(path = "/reports",
             consumes = MediaType.APPLICATION_JSON_VALUE,
             produces = MediaType.APPLICATION_JSON_VALUE)
public ReportResponse create(@RequestBody ReportRequest request) {
    // ...
}
```

Đây là method minh họa; `ReportRequest`/`ReportResponse` là DTO giả định. Nếu client gửi `Content-Type: text/plain`, mapping JSON không thỏa: HTTP **415 Unsupported Media Type** thường được trả về. Nếu client gửi JSON hợp lệ nhưng `Accept: application/xml` và endpoint chỉ tạo JSON, server có thể trả **406 Not Acceptable**. Nếu client gửi `Content-Type: application/json` nhưng JSON sai cú pháp, converter đã được chọn mà việc đọc thất bại: thường **400 Bad Request**.

Bốn khía cạnh khác nhau:

1. **Endpoint matching:** Spring chọn method có route và media conditions khớp.
2. **Reader compatibility:** kiểu tham số Java + request media type phải được converter đọc được.
3. **Writer compatibility:** kiểu trả về Java + negotiated response media type phải được converter ghi được.
4. **Dữ liệu hợp lệ:** payload phải parse được, dữ liệu deserialize được và đạt các constraint cần thiết.

Đừng nhầm `Accept` với `Content-Type`: gửi JSON vào không có nghĩa client bắt buộc phải nhận JSON ra; hai chiều độc lập. Việc thương lượng media type có thể chịu ảnh hưởng bởi cấu hình `ContentNegotiationConfigurer`, headers, converter được đăng ký và handler mapping. Trong API hiện đại, header `Accept` là phương tiện tiêu biểu.

Các vấn đề encoding cũng thuộc biểu diễn body: `Content-Type: text/plain;charset=UTF-8` cho biết charset của text; JSON hiện đại thông thường dùng UTF-8. Không tự chuyển binary thành `String` nếu cần bảo toàn byte chính xác. `String.length()` trong Java đếm đơn vị mã UTF-16, còn HTTP `Content-Length` nói về **số byte**, hai giá trị không nhất thiết bằng nhau.

## 8. Ví dụ Spring MVC đầy đủ chạy được với Java 17

Ví dụ minh họa ba dạng request body (JSON/text/binary) và ba dạng response (JSON/text/binary). Đây là ứng dụng thực thi được; không cần database.

Cấu trúc:

```text
mvc-converters-demo/
├── pom.xml
└── src/main/java/demo/converter/
    ├── ConverterApplication.java
    └── BodyController.java
```

**`pom.xml`**

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
    <groupId>demo</groupId>
    <artifactId>mvc-converters-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

**`src/main/java/demo/converter/ConverterApplication.java`**

```java
package demo.converter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConverterApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConverterApplication.class, args);
    }
}
```

**`src/main/java/demo/converter/BodyController.java`**

```java
package demo.converter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class BodyController {

    public record EchoInput(@NotBlank String message,
                            @Min(1) int copies) {}

    public record EchoOutput(String echoed, int utf16Units) {}

    @PostMapping(path = "/messages",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<EchoOutput> createMessage(
            @Valid @RequestBody EchoInput input) {

        String echoed = input.message().repeat(input.copies());
        EchoOutput result = new EchoOutput(echoed, echoed.length());

        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Converted-By", "spring-mvc")
                .body(result);
    }

    @PostMapping(path = "/plain",
                 consumes = MediaType.TEXT_PLAIN_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> readPlain(@RequestBody String text) {
        return ResponseEntity.ok("text:" + text);
    }

    @PostMapping(path = "/bytes",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Integer> readBytes(@RequestBody byte[] bytes) {
        return Map.of("byteCount", bytes.length);
    }

    @GetMapping(path = "/download",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> download() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"sample.bin\"")
                .body(new byte[]{65, 66, 67});
    }

    @GetMapping(path = "/health-text",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String healthText() {
        return "ready";
    }
}
```

Giải thích điểm then chốt của từng endpoint:

- `/api/messages`: Jackson JSON converter đọc request JSON thành `EchoInput`; `@Valid` kiểm tra message không trống và copies ít nhất bằng 1; controller tạo `EchoOutput`; JSON converter ghi response status `201` kèm header tùy chỉnh.
- `/api/plain`: `StringHttpMessageConverter` đọc và ghi text. Phần body chỉ là text; không có JSON escaping.
- `/api/bytes`: `ByteArrayHttpMessageConverter` đọc bytes không diễn giải chúng là text; controller trả `Map` để Jackson ghi response JSON.
- `/api/download`: controller tạo ba byte `65,66,67`, converter byte array ghi ra HTTP output và `Content-Disposition` đề xuất tên file.
- `/api/health-text`: `@RestController` bảo đảm chuỗi trả về là **response body**, không được hiểu là tên template view.

Chạy từ thư mục chứa `pom.xml`, với JDK 17+ và Maven được cài đặt:

```bash
mvn spring-boot:run
```

### 8.1. JSON vào, JSON ra

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"message":"Hi","copies":2}'
```

Phần status, header và body dự kiến:

```http
HTTP/1.1 201
Content-Type: application/json
X-Converted-By: spring-mvc

{"echoed":"HiHi","utf16Units":4}
```

Giá trị `4` ở đây là `"HiHi".length()`, không phải mặc định biểu diễn độ dài mọi chuỗi Unicode. Thứ tự thuộc tính JSON ở đây là cách biểu diễn điển hình; test client nên so sánh các field, không dựa vào thứ tự keys.

### 8.2. Text vào, text ra

```bash
curl -s -X POST http://localhost:8080/api/plain \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'Hello MVC'
```

Response body chính xác:

```text
text:Hello MVC
```

`--data-binary` giúp gửi đúng dữ liệu text của ví dụ. Nếu cần gửi ký tự quốc tế, hãy thống nhất UTF-8 ở client, headers và converter.

### 8.3. Bytes vào, JSON ra

```bash
curl -s -X POST http://localhost:8080/api/bytes \
  -H 'Content-Type: application/octet-stream' \
  -H 'Accept: application/json' \
  --data-binary 'ABC'
```

Response body:

```json
{"byteCount":3}
```

Đây là ba byte ASCII `A=65`, `B=66` và `C=67`. Khi upload dữ liệu lớn, không nên luôn đọc toàn bộ body vào `byte[]`; phải cân nhắc giới hạn payload, multipart handling hoặc streaming chuyên biệt.

### 8.4. Bytes ra, tải về tệp

```bash
curl -s -D headers.txt \
  -o sample.bin \
  http://localhost:8080/api/download
```

Tệp `sample.bin` có ba byte `41 42 43` ở hệ hex, tức `ABC` ở ASCII. Header có giá trị quan trọng:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="sample.bin"
```

Lệnh `-D` chỉ lưu response headers vào `headers.txt`; `-o` lưu response body vào `sample.bin`. Đừng dùng chế độ hiển thị terminal để kiểm tra binary tùy ý, vì byte có thể không phải text đọc được.

### 8.5. Lỗi do dữ liệu hoặc media type

Gửi sai constraint:

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"","copies":0}'
```

Dự kiến response status `400 Bad Request` vì `@NotBlank` và `@Min(1)` không đạt. Hình dạng JSON lỗi mặc định có thể thay đổi theo cấu hình Spring Boot và exception handling; không nên đưa một JSON error body giả định thành contract.

Gửi sai request media type:

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: text/plain' \
  --data-binary '{"message":"Hi","copies":2}'
```

Thường nhận `415 Unsupported Media Type` vì mapping `consumes` chỉ nhận JSON, mặc dù nội dung text trông giống JSON. Server dùng **header thật sự**, không nhìn ký tự `{` để tự suy luận định dạng.

Gửi Accept không khớp:

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/xml' \
  -d '{"message":"Hi","copies":2}'
```

Thường nhận `406 Not Acceptable` vì mapping `produces` chỉ công bố JSON. Lệnh này minh họa **đầu ra** không được client chấp nhận.

### 8.6. Thử bằng PowerShell

Nếu shell đang dùng PowerShell, có thể gửi request JSON không phụ thuộc cú pháp xuống dòng của Bash:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/messages' -ContentType 'application/json' -Body '{"message":"Hi","copies":2}'
```

PowerShell thường deserialize JSON thành đối tượng khi dùng `Invoke-RestMethod`, nên đầu ra terminal không nhất thiết là nguyên văn JSON bytes; dùng `Invoke-WebRequest` hoặc công cụ HTTP khác nếu muốn đối chiếu status/headers/raw representation.

## 9. Tùy biến danh sách message converters

Với Spring MVC 6.1, `WebMvcConfigurer` có hai extension points thường dùng:

```java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Khai báo danh sách theo chủ đích.
}

@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Điều chỉnh danh sách đã được cấu hình.
}
```

Hai method này là **đoạn minh họa**, không phải một lớp đầy đủ có imports. Trong Spring MVC tự cấu hình bằng `WebMvcConfigurer`, dùng `configureMessageConverters` để khai báo converter tùy chỉnh có thể **thay thế thiết lập converter mặc định**; dùng `extendMessageConverters` để bổ sung vào danh sách đã có thường ít rủi ro hơn. Với Spring Boot, cũng có cơ chế tự phát hiện các `HttpMessageConverter` beans; phải xem behavior của version và tránh đăng ký trùng converter.

Không sửa thứ tự converter tùy tiện. Nếu converter quá rộng được đặt trước JSON converter và luôn báo `canRead`/`canWrite` là true cho mọi kiểu, nó có thể chọn nhầm và phá vỡ những endpoint bình thường.

### Ví dụ converter cho text/x-compact

Giả sử ứng dụng cần media type riêng `text/x-compact` để trao đổi một dòng văn bản. Converter mẫu bên dưới được tách thành ba snippet; chúng có thể được thêm vào **ứng dụng ở mục 8** trong cùng package `demo.converter`. Đây là phần mở rộng tùy chọn, ứng dụng ở mục 8 chạy độc lập mà không cần các file này.

**`CompactLine.java`**

```java
package demo.converter;

public record CompactLine(String value) {}
```

**`CompactLineConverter.java`**

```java
package demo.converter;

import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class CompactLineConverter
        extends AbstractHttpMessageConverter<CompactLine> {

    public CompactLineConverter() {
        super(new MediaType(
                "text", "x-compact", StandardCharsets.UTF_8));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return CompactLine.class == clazz;
    }

    @Override
    protected CompactLine readInternal(
            Class<? extends CompactLine> clazz,
            HttpInputMessage input) throws IOException {
        byte[] raw = input.getBody().readAllBytes();
        return new CompactLine(
                new String(raw, StandardCharsets.UTF_8));
    }

    @Override
    protected void writeInternal(
            CompactLine line, HttpOutputMessage output)
            throws IOException {
        output.getBody().write(
                line.value().getBytes(StandardCharsets.UTF_8));
    }
}
```

**`CompactConverterConfiguration.java`**

```java
package demo.converter;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

@Configuration
public class CompactConverterConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new CompactLineConverter());
    }
}
```

**Thêm hai method sau vào `BodyController`**; cần import `org.springframework.web.bind.annotation.GetMapping` (file chính đã có `GetMapping`) và dùng record `CompactLine` cùng package:

```java
@PostMapping(path = "/compact",
             consumes = "text/x-compact",
             produces = "text/x-compact")
public CompactLine compact(@RequestBody CompactLine input) {
    return new CompactLine(input.value().toUpperCase(
            java.util.Locale.ROOT));
}

@GetMapping(path = "/compact",
            produces = "text/x-compact")
public CompactLine compactExample() {
    return new CompactLine("hello");
}
```

Hai method là **đoạn cần chèn vào class controller**, không phải file Java đứng riêng. Client:

```bash
curl -s -X POST http://localhost:8080/api/compact \
  -H 'Content-Type: text/x-compact' \
  -H 'Accept: text/x-compact' \
  --data-binary 'hello'
```

Response body:

```text
HELLO
```

Lưu ý về converter tùy biến:

- `supports` chỉ cho class `CompactLine`; `new MediaType(...)` giới hạn media type. Thiết kế hẹp tránh tranh chấp với converter mặc định.
- `readInternal` đọc bytes rồi giải mã UTF-8; `writeInternal` mã hóa giá trị thành UTF-8. Đây là converter demo, **chưa xử lý validation cấu trúc, độ dài, ký tự cấm hoặc giới hạn request size**.
- `readAllBytes()` nạp toàn body vào RAM: chỉ dùng khi request đã được giới hạn dung lượng. Với stream lớn cần thiết kế khác.
- `extendMessageConverters` bảo toàn danh sách mặc định; chèn converter ở đầu trong ví dụ giúp media type riêng được xử lý trước các converter rộng. Trong sản phẩm thật, xem xét sự xung đột của các media types đã đăng ký.
- Nếu định dạng chỉ là JSON với cách đặt tên field khác, thường **cấu hình Jackson ObjectMapper/serializer** thích hợp hơn viết một converter thủ công.
- Converter chỉ đảm nhận body. Endpoint vẫn cần mapping `consumes`/`produces`, validation và error handling đúng như bình thường.

## 10. RequestBodyAdvice và ResponseBodyAdvice nằm ở đâu?

Spring MVC còn cung cấp extension points để can thiệp ở các điểm quanh quá trình chuyển đổi:

- `RequestBodyAdvice` có thể can thiệp khi request body chuẩn bị được đọc hoặc vừa chuyển thành object cho các tham số như `@RequestBody`/`HttpEntity`, tùy phase và method mà advice triển khai.
- `ResponseBodyAdvice` được gọi ở bước chuẩn bị ghi return value, sau khi một converter đã được chọn và trước khi body được ghi ra response.

Các advice thường được khai báo thông qua `@ControllerAdvice` và có `supports(...)` để chọn phạm vi phù hợp. Chúng hữu ích khi có yêu cầu thống nhất về envelope, auditing metadata hoặc điều chỉnh representation. Tuy nhiên:

- Không nên dùng advice để lén đổi contract JSON mà client không biết.
- Nếu `ResponseBodyAdvice` thay object bằng kiểu mà converter đã chọn **không thể ghi**, request có thể lỗi ở bước output. Đặc biệt phải thận trọng với response kiểu `String`.
- Không dùng advice để đọc lại request body nếu request stream đã tiêu thụ; tránh log nội dung nhạy cảm.
- Authentication, authorization, request size và business validation có vị trí xử lý riêng, không được xem advice là giải pháp thay thế.

## 11. Lỗi thường gặp và cách phân tích

| Dấu hiệu | Giai đoạn thường gặp | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| `415 Unsupported Media Type` | Mapping/chọn request reader | Header `Content-Type` không khớp `consumes` hoặc không có converter phù hợp |
| `406 Not Acceptable` | Negotiation/chọn response writer | `Accept` không khớp `produces` hoặc không có converter viết được |
| `400 Bad Request` | Request conversion hoặc validation | JSON hỏng, body thiếu, field type sai, constraint lỗi |
| `HttpMessageNotReadableException` | Converter đọc request | Deserialize thất bại, dữ liệu không theo cấu trúc cần thiết |
| `MethodArgumentNotValidException` | Validation sau khi tạo argument | Object vi phạm Bean Validation, khi không xử lý qua `BindingResult` |
| `HttpMessageNotWritableException` | Converter ghi response | Serialize thất bại, mapper không ghi được object |
| Response trống hoặc khác mong đợi | Return-value processing | Method trả view name thay vì body, status `204`, body `null`, converter khác được chọn |
| Chữ Unicode bị méo | Đọc/ghi text | Charset của client/server không khớp |
| Tệp bị lỗi | Binary representation | Biến bytes thành String, nhầm media type hoặc xử lý stream sai |

Một số HTTP status là **kết quả thường gặp**, không bảo đảm tuyệt đối cho mọi cấu hình. Ví dụ: một serialization failure có thể dẫn đến lỗi server, nhưng exception handler/custom response cũng có thể thay đổi status. Để chẩn đoán chính xác, hãy ghi lại **request method, URL, Content-Type, Accept, declared DTO return type, mapping consumes/produces, converter list, exception class và stack trace liên quan**. Không ghi raw payload nhạy cảm hoặc secrets vào log.

Quy trình kiểm tra ngắn:

1. Dùng `curl -i` hoặc công cụ tương đương để nhìn **request/response headers và status**.
2. Kiểm tra routing và `consumes`/`produces` trước.
3. Kiểm tra converter cho kiểu tham số/return type; nhớ thứ tự.
4. Kiểm tra JSON/form/charset và validation sau khi đã xác nhận được converter.
5. Xem exception gốc nếu có, trước khi bổ sung custom advice hoặc converter.
6. Khi đổi cấu hình, thử lại từng media type hiện có để phát hiện ảnh hưởng ngoài ý muốn.

### Một số sai lầm điển hình

**Sai: nhầm String với JSON DTO.**

```java
@GetMapping(produces = "application/json")
@ResponseBody
public String value() {
    return "hello"; // Đừng tự cho rằng converter sẽ tạo JSON string hợp lệ.
}
```

Đây là method minh họa. Nếu muốn JSON đúng định dạng, hãy trả DTO/record như `new MessageResponse("hello")` để mapper serialize, hoặc dùng explicit representation khi đã hiểu converter được chọn. JSON string hợp lệ cần dấu nháy và escaping theo tiêu chuẩn JSON; text thông thường không tự là JSON.

**Sai: đọc request stream hai lần.**

```java
public void handle(@RequestBody byte[] bytes,
                   HttpServletRequest request) {
    // Không kỳ vọng request.getInputStream() còn nguyên body ban đầu.
}
```

Đây chỉ là chữ ký minh họa. Request body thông thường là stream tiêu thụ một lần. Một filter đọc stream trước cũng có thể làm controller thấy body rỗng. `ContentCachingRequestWrapper` chỉ cache dữ liệu **đã đọc qua wrapper**, không tự cho phép đọc lại body tùy ý. Nếu cần bảo toàn raw body để kiểm tra chữ ký, thiết kế filter/wrapper và giới hạn dung lượng cẩn thận.

**Sai: tự thêm converter wildcard.** Nếu một converter tùy biến hỗ trợ `Object.class` và `*/*`, nó có thể giành xử lý từ Jackson hoặc String converters, khiến những endpoint không liên quan thay đổi output. Hãy hạn chế class và media type theo đúng format mới.

**Sai: coi message conversion là authentication hoặc schema security.** Deserialize JSON thành entity có property nhạy cảm có thể dẫn đến over-posting; luôn dùng input DTO riêng, validation thích hợp và chỉ map các field được phép vào domain model. Không tự tin rằng converter đã bảo vệ dữ liệu người dùng.

## 12. Quy tắc chọn giải pháp

| Trường hợp | Cách giải quyết thường phù hợp |
| --- | --- |
| Client gửi JSON và cần DTO Java | `@RequestBody` + JSON converter + validation |
| Client gửi một chuỗi nguyên văn | `@RequestBody String` và media type text |
| Client gửi raw binary kích thước vừa phải | `@RequestBody byte[]`; chú ý giới hạn dung lượng |
| Client gửi HTML form | `@RequestParam` / `@ModelAttribute` |
| Client gửi multipart file/part | `MultipartFile` / `@RequestPart` và multipart resolver |
| Controller trả dữ liệu JSON | Trả DTO/record qua `@RestController` hoặc `ResponseEntity<T>` |
| Trả body với status/headers cụ thể | `ResponseEntity<T>` |
| Tải file | `ResponseEntity<Resource>` hoặc `byte[]` với media type và headers đúng |
| Thêm format wire protocol riêng | Tạo `HttpMessageConverter<T>` hẹp, đăng ký đúng thứ tự |
| Chỉ đổi serialization JSON | Tùy chỉnh Jackson thay vì viết converter từ đầu |

Lưu ý rằng converter và type conversion của `WebDataBinder` là **hai mảng khác nhau**. Ví dụ form field `age=20` thành `int` qua binding infrastructure khác với chuyển JSON `{"age":20}` thành record qua Jackson. Cả hai có thể dùng Bean Validation nhưng khác ở đường đưa dữ liệu vào object.

## 13. Câu hỏi tự kiểm tra và thử nghiệm

1. Client gửi `Content-Type: text/plain` vào endpoint `consumes="application/json"`. Spring kiểm tra điều gì trước khi Jackson được gọi?
2. Nếu `@RestController` trả `String`, tại sao không nên mặc nhiên kết luận rằng response body là JSON?
3. Hai hướng `canRead` và `canWrite` khác nhau ra sao? Một converter có thể chỉ hỗ trợ một chiều không?
4. Khi client đặt `Accept: application/xml`, server chỉ có JSON writer và endpoint `produces="application/json"`, vì sao thường nhận `406`?
5. Vì sao `@Valid` không thể thay thế deserialize? Vì sao deserialize thành công chưa đảm bảo dữ liệu hợp lệ?
6. Vì sao `ByteArrayHttpMessageConverter` có thể thích hợp hơn `StringHttpMessageConverter` cho nội dung PDF/ZIP?
7. Trong Spring MVC 6.1, khi nào nên chọn `extendMessageConverters` thay vì `configureMessageConverters`?
8. Vì sao `HttpMessageConverter` mới không nên khai báo `supports(Object.class)` và `*/*` một cách quá rộng?
9. Nếu trả `ResponseEntity<Void>` với status `204`, Spring có cần gọi writer để serialize JSON DTO không?
10. Điều gì xảy ra nếu đặt một converter mới lên đầu danh sách và nó báo đọc được tất cả kiểu Java, bất kể media type?

**Gợi ý:** (1) Mapping `consumes`/media type request. (2) String converter thường ghi text. (3) Một hướng là parse bytes vào Java, hướng kia serialize Java ra bytes; năng lực phụ thuộc converter. (4) Không có representation phù hợp client. (5) Converter tạo object, validator kiểm tra ràng buộc. (6) Phải giữ nguyên byte. (7) Để giữ danh sách converter mặc định rồi bổ sung. (8) Tránh giành xử lý không chủ ý. (9) Không có body để serialize. (10) Có thể chọn nhầm converter và phá response/request hiện tại.

## 14. Tài liệu chính thức

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.2 — Configuring Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html)
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework 6.1 — HttpMessageConverter API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/converter/HttpMessageConverter.html)
- [Spring Framework 6.1 — MappingJackson2HttpMessageConverter API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/converter/json/MappingJackson2HttpMessageConverter.html)
- [Spring Framework 6.1 — WebMvcConfigurer API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)

Tài liệu tham khảo có cả bản 6.x và trang hiện hành để tra cứu ý tưởng, nhưng các ví dụ code đã chọn API/kiểu cấu hình tương thích với **Spring Framework 6.1 / Spring Boot 3.3.5**.