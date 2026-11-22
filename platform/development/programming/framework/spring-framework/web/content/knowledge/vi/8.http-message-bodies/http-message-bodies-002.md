# Chọn bộ chuyển đổi cho chuỗi, byte[], Resource, JSON và XML trong Spring MVC

> **Phạm vi:** Spring Web MVC (Servlet stack) chạy với Java 17+ và ví dụ Spring Boot 3.x / Spring Framework 6.x. Bài học tập trung vào cách Spring đọc và ghi **HTTP message body** qua `HttpMessageConverter` khi controller nhận `@RequestBody`, trả `@ResponseBody` hoặc `ResponseEntity<?>`. Năm nhóm giá trị cần phân biệt là **`String`, `byte[]`, `Resource`, object JSON và object XML**. Tên converter Jackson trong Spring Framework 7 có thay đổi; phần code demo dùng API tương thích nhánh Spring 6.x.

## 1. HTTP body và converter: vấn đề cần giải quyết

Một handler có thể trả về rất nhiều loại Java:

```java
@GetMapping("/hello")
public String hello() {
    return "Xin chào";
}

@GetMapping("/profile")
public ProfileDto profile() {
    return new ProfileDto(7, "Lan");
}
```

Cả hai đều là giá trị Java nhưng wire format khác nhau:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

Xin chào
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"Lan"}
```

Spring MVC không tự đoán rằng mọi `String` đều là JSON hay mọi object đều là XML. Khi giá trị đi qua xử lý body, framework chọn một `HttpMessageConverter` có thể xử lý **kiểu dữ liệu Java** và **media type** hiện hành. Converter phụ trách biến body từ byte HTTP thành object Java (đọc), hoặc object Java thành byte HTTP (ghi).

Ghi nhớ vai trò của từng thành phần:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `@RequestBody` | Yêu cầu Spring đọc **request body** thành đối số Java |
| `@ResponseBody` / `@RestController` | Yêu cầu Spring ghi giá trị trả về thành **response body** |
| `ResponseEntity<T>` | Cung cấp status, headers và body; body vẫn thường đi qua converter |
| `HttpMessageConverter<T>` | Đọc/ghi body với kiểu Java và media type nó hỗ trợ |
| Request `Content-Type` | Client thông báo **định dạng body đang gửi lên** |
| Request `Accept` | Client thông báo **định dạng phản hồi có thể nhận** |
| Response `Content-Type` | Server công bố **định dạng body thực tế trả về** |
| Mapping `consumes` / `produces` | Giới hạn media type của route cho request/response |

**Hai chiều phải phân biệt:** với `@RequestBody`, Spring xét kiểu tham số Java và request `Content-Type`; với `@ResponseBody`, Spring xét kiểu giá trị trả về, những converter có thể ghi, `Accept` và các ràng buộc `produces`, `Content-Type` đã đặt.

## 2. Bộ converter thường gặp cho năm nhóm dữ liệu

| Giá trị Java | Converter Spring MVC phổ biến | Media type cần chú ý | Ví dụ dùng |
| --- | --- | --- | --- |
| `String` | `StringHttpMessageConverter` | Chủ yếu body văn bản, thường trả `text/plain` nếu không chọn khác | Text, CSV tự xây, nội dung chữ |
| `byte[]` | `ByteArrayHttpMessageConverter` | Hỗ trợ rộng `*/*`; mặc định ghi `application/octet-stream` | Binary payload nhỏ, dữ liệu đã ở bộ nhớ |
| `Resource` | `ResourceHttpMessageConverter` | Dữ liệu resource/file; thường `application/octet-stream` hoặc media type khai báo | Trả file, tải xuống, byte stream từ nguồn tài nguyên |
| POJO/record JSON | `MappingJackson2HttpMessageConverter` | `application/json`, thường có `application/*+json` | REST JSON API |
| POJO/record XML | `MappingJackson2XmlHttpMessageConverter` | `application/xml`, `text/xml` và XML suffix khi được hỗ trợ | Tích hợp XML / content negotiation |

Tên Jackson 2 converter trong bảng đúng với **Spring Framework 6.x**. Từ Spring Framework 7.x, hệ API converter được cập nhật cho Jackson thế hệ mới; cần đối chiếu tài liệu đúng version trước khi khai báo hoặc tùy biến class converter. Các API controller chung như `@RequestBody`, `ResponseEntity`, `produces` và `consumes` vẫn là cơ chế quan trọng.

Một nhóm khác trong Spring là `FormHttpMessageConverter` cho `application/x-www-form-urlencoded` / multipart ở phạm vi tương ứng, nhưng không phải đối tượng chính của bài này. Không nên dùng `StringHttpMessageConverter` để tự viết JSON/XML khi một converter chuyên dụng và DTO rõ kiểu đáp ứng yêu cầu tốt hơn.

### 2.1. Converter có phải lúc nào cũng sẵn?

Không. Một số converter đi kèm Spring Web; converter JSON/XML phụ thuộc thư viện serialization tương ứng trên classpath và cấu hình MVC. Spring Boot thường tự cấu hình một tập converter phù hợp với dependency. Ví dụ:

- Thêm **Spring Web** trên dự án Spring Boot 3.x thông thường mang theo Jackson JSON.
- Để dùng Jackson XML trong ví dụ, cần thêm `com.fasterxml.jackson.dataformat:jackson-dataformat-xml` đúng version do Spring Boot quản lý.
- Nếu không có XML converter phù hợp, dù client gửi `Accept: application/xml`, Spring **không thể tự động tạo XML từ mọi Java object** chỉ bằng đổi header.
- Một hệ thống có thể chủ động thay đổi/thứ tự converter, media types được hỗ trợ hoặc `ObjectMapper`. Không xem bảng là lời cam kết cố định của mọi ứng dụng.

## 3. Quy trình chọn converter ở tầng controller

Sơ đồ khái niệm:

```text
                      HTTP request
                           |
       +-------------------+---------------------+
       |                                         |
@RequestBody T                              Handler execution
       |                                         |
Content-Type + T                           Return value (T)
       |                                         |
canRead(T, media type)?                    @ResponseBody / ResponseEntity
       |                                         |
read(...) -> T                            Accept + produces + Content-Type
       |                                         |
Controller sử dụng object                   canWrite(T, media type)?
                                                 |
                                             write(...) -> HTTP body
```

Khi Spring xử lý request, có hai giai đoạn khác nhau:

1. **Chọn handler**: `@RequestMapping` và các biến thể `@GetMapping`, `@PostMapping` có thể giới hạn route bằng `consumes` và `produces`; không thỏa các điều kiện này có thể loại mapping trước khi converter chạy.
2. **Đọc/ghi body**: một converter được đăng ký phải hỗ trợ kiểu Java và media type hợp lệ. Với response, Spring còn thực hiện content negotiation, thường dựa trên `Accept` và kiểu body.

Thứ tự converter **có thể ảnh hưởng** khi nhiều converter đều tuyên bố xử lý được cùng một Java type/media type. Spring kiểm tra những converter phù hợp trong danh sách đã đăng ký. Vì vậy custom converter khai báo quá rộng như `*/*` hoặc chèn lên đầu danh sách có thể làm thay đổi output khác dự kiến.

### 3.1. Phân biệt ba vị trí đặt media type

```java
@PostMapping(
    path = "/documents",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public DocumentDto create(@RequestBody DocumentDto input) {
    return input;
}
```

- `consumes = application/json` có nghĩa method mong request body là JSON. Client cần gửi `Content-Type: application/json`.
- `produces = application/json` có nghĩa method tạo response JSON, client nên chấp nhận `application/json` trong header `Accept`.
- `ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(...)` đặt response `Content-Type` cụ thể. Nó **không bắt Spring biến một `String` tùy ý thành JSON hợp lệ**.

Khi client gửi body XML tới route chỉ `consumes = application/json`, kết quả thông thường là **415 Unsupported Media Type**. Khi client chỉ chấp nhận XML nhưng route chỉ `produces = application/json`, kết quả thường là **406 Not Acceptable**. Ngoài ra, nếu định dạng được chấp nhận về mặt header nhưng body sai cú pháp/không giải mã được, thường nhận **400 Bad Request** do lỗi đọc request.

## 4. `StringHttpMessageConverter` — trả hoặc nhận văn bản

Ví dụ text response:

```java
@GetMapping(path = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
public String hello() {
    return "Xin chào Spring MVC";
}
```

Vì method thuộc `@RestController` (hoặc có `@ResponseBody`), Spring ghi chuỗi vào body, không coi chuỗi là tên view. Kiểu dữ liệu trả về là `String` nên converter dành cho String thường được chọn và tạo body text.

Các điều cần nhớ:

- `StringHttpMessageConverter` đọc/ghi chuỗi, không đóng vai trò mapping JSON object sang DTO.
- `Content-Type` được xác định bởi mapping, headers và negotiation; nếu muốn nội dung văn bản cụ thể, dùng `produces = "text/plain"` hoặc đặt rõ content type với `ResponseEntity`.
- Với Unicode, cần mã hóa đúng. Ở Spring Boot hiện đại, UTF-8 thường được dùng cho text; có thể khai báo rõ `text/plain;charset=UTF-8` ở output contract khi cần.
- `String` chứa `{"ok":true}` vẫn chỉ là các ký tự. Việc đặt `produces = "application/json"` **không tự kiểm tra** chuỗi ấy là JSON hợp lệ. Có thể vô tình trả JSON sai cú pháp.
- Nếu muốn JSON string scalar (ví dụ response JSON hợp lệ là `"hello"` với dấu nháy ở body), cần hiểu sự khác biệt giữa String converter và Jackson. Tốt nhất trả DTO/object khi xây API JSON để tránh hành vi lựa chọn converter tùy cấu hình.

Ví dụ nhận text:

```java
@PostMapping(
        path = "/echo-text",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
public String echoText(@RequestBody String body) {
    return "text: " + body;
}
```

Với `Content-Type: text/plain` và body `Java`, server trả body `text: Java`. `@RequestBody` đọc **body** chứ không phải query string. Nếu chỉ có `?body=Java` mà body trống, method có `@RequestBody` bắt buộc có thể nhận lỗi vì thiếu body.

## 5. `ByteArrayHttpMessageConverter` — `byte[]` nguyên bản

Một mảng byte là dữ liệu byte **đã ở bộ nhớ**:

```java
@GetMapping(path = "/bytes", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<byte[]> bytes() {
    byte[] data = new byte[] {0x41, 0x42, 0x43};
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(data);
}
```

Body HTTP gồm chính xác ba byte hexa `41 42 43`, tương ứng chữ ASCII `ABC`. Không có thêm dấu nháy JSON, Base64 hoặc các ký tự JSON array.

Dùng `byte[]` khi:

- Body nhỏ hoặc vừa và đã cần toàn bộ byte trong RAM.
- Đọc/ghi binary protocol, dữ liệu nén hoặc file rất nhỏ.
- Cần kiểm soát **chính xác các byte** sau khi qua HTTP converter, không muốn serialization sang JSON.

Không dùng `byte[]` để đọc toàn bộ file rất lớn chỉ nhằm gửi cho client; nó buộc ứng dụng giữ nội dung trong bộ nhớ. Khi nguồn nội dung là file hoặc một tài nguyên có thể mở stream, xem `Resource` ở mục 6.

Nếu client gửi binary lên:

```java
@PostMapping(
        path = "/byte-count",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
public String byteCount(@RequestBody byte[] body) {
    return "bytes=" + body.length;
}
```

Nếu client gửi ba byte `ABC` với `Content-Type: application/octet-stream`, body phản hồi là `bytes=3`. Đếm ở đây là **số byte**, không phải số ký tự Unicode.

Media type mặc định của `ByteArrayHttpMessageConverter` khi ghi thường là `application/octet-stream` dù converter hỗ trợ nhiều media type. Trong REST, đặt rõ `Content-Type` theo ý nghĩa thực của dữ liệu (ví dụ ảnh PNG có thể là `image/png`), không giả định client có thể đoán định dạng từ file extension.

## 6. `ResourceHttpMessageConverter` — trả về tài nguyên/file

`org.springframework.core.io.Resource` là abstraction cho dữ liệu có thể truy cập qua nguồn tài nguyên, chẳng hạn `ClassPathResource`, `FileSystemResource`, `ByteArrayResource` hoặc một nguồn stream thích hợp. Spring MVC có thể ghi nội dung `Resource` ra response thông qua `ResourceHttpMessageConverter`.

Ví dụ download một file nhúng:

```java
@GetMapping(path = "/download", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<Resource> download() {
    Resource body = new ByteArrayResource(
            "FILE\n".getBytes(StandardCharsets.UTF_8));

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"example.txt\"")
            .body(body);
}
```

Khi client gọi `GET /download`, server gửi header `Content-Disposition: attachment; filename="example.txt"` và **5 byte** của `FILE` cộng một newline. `ByteArrayResource` ở đây chỉ nhằm minh họa bằng dữ liệu tự tạo; với file có sẵn, có thể dùng `FileSystemResource` hoặc `PathResource` theo chính sách cho phép truy cập.

### 6.1. `byte[]` và `Resource` khác nhau thế nào?

| Câu hỏi | `byte[]` | `Resource` |
| --- | --- | --- |
| Cách biểu diễn | Nội dung nằm trong một mảng byte | Handle/abstraction tới nội dung |
| Bộ nhớ | Thường giữ toàn bộ body trong RAM | Có thể lấy dữ liệu từ file/stream khi ghi |
| File lớn | Không lý tưởng | Thường thích hợp hơn nếu loại Resource và hạ tầng phù hợp |
| Converter chính | `ByteArrayHttpMessageConverter` | `ResourceHttpMessageConverter` |
| Metadata file | Tự đặt header | Cũng cần chủ động đặt `Content-Type`, `Content-Disposition` khi cần |
| Streaming | Trả ngay byte đã có | Có thể mở stream lúc ghi, tùy `Resource` |

**Quan trọng với streaming:** `Resource` không bảo đảm mọi triển khai đều tái mở stream được. `InputStreamResource` có thể chỉ đọc một lần, và tính Content-Length có thể tiêu thụ stream nếu dùng subclass/bọc không đúng. Với `InputStreamResource` cần hiểu quy ước lazy stream supplier và giới hạn hỗ trợ; tránh vừa đọc thử stream để đo độ dài rồi lại yêu cầu converter đọc tiếp. Với file thường, chọn Resource thích hợp cho phép hệ thống xử lý kích thước/streaming thuận tiện hơn.

### 6.2. Download, cache và HTTP Range

Các response trả `Resource` có thể liên quan đến partial-content/Range support của Spring MVC trong những điều kiện nhất định. Không đồng nhất `Resource` với việc **mọi endpoint đều tự hỗ trợ resumable download**. Chức năng phụ thuộc cách controller trả Resource, loại Resource, headers, cấu hình và hạ tầng HTTP.

Nếu cần download production:

1. Xác định quyền người dùng đối với file trước khi tạo `Resource`.
2. Không nối trực tiếp path từ query hoặc URL để đọc file nếu chưa chuẩn hóa và kiểm tra path traversal.
3. Đặt `Content-Type` chính xác; nếu cần download thay vì hiển thị trực tiếp, đặt `Content-Disposition: attachment` với filename đã xử lý an toàn.
4. Kiểm tra Content-Length, memory profile, Range, timeout, file không tồn tại và lỗi I/O bằng integration test với file đủ lớn.

## 7. JSON — `MappingJackson2HttpMessageConverter`

JSON converter biến body như sau thành object Java:

```http
POST /api/messages/json
Content-Type: application/json
Accept: application/json

{"text":"Chao ban"}
```

Controller:

```java
@PostMapping(
        path = "/messages/json",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public MessageDto echoJson(@RequestBody MessageDto input) {
    return input;
}
```

Với kiểu `record MessageDto(String text) { }`, Jackson deserializer đọc JSON thành Java object; Jackson serializer ghi object đó thành JSON. Cần Jackson JSON (thường có sẵn khi thêm Spring Boot starter web phù hợp với Boot 3.x).

### 7.1. Tại sao nên trả DTO thay vì chuỗi JSON tự nối?

Không nên:

```java
// Anti-pattern: ghép JSON thủ công.
return "{\"text\":\"" + userInput + "\"}";
```

Đoạn nối chuỗi trên không xử lý đầy đủ dấu nháy, xuống dòng, escape và các trường hợp đặc biệt. Với JSON API hãy dùng DTO/record và để Jackson serialize:

```java
public record MessageDto(String text) {
}
```

Đây là **định nghĩa type minh họa**; khi đặt trong cùng file chứa `public class DemoApplication`, bỏ `public` của record hoặc tách thành file `MessageDto.java`. Việc trả `MessageDto` đảm bảo serializer phù hợp với kiểu object và các quy tắc escape cần thiết.

### 7.2. JSON không phải là một media type cho mọi giá trị

Nếu response thực sự là file/binary nhưng chỉ đặt `application/json`, client có thể hiểu sai. Nếu endpoint có thể trả hai biểu diễn cho **cùng một object**, cần cài các converter và sử dụng content negotiation rõ ràng. Trong API production, schema DTO phải phù hợp và không trực tiếp serialize entity chứa thông tin nhạy cảm.

Với JSON request, `@Valid @RequestBody MessageDto input` có thể chạy Bean Validation nếu được cấu hình và có dependency phù hợp. Conversion chỉ là **bước đọc**, không phải xác thực dữ liệu hay phân quyền.

## 8. XML — `MappingJackson2XmlHttpMessageConverter`

XML converter là một lựa chọn riêng với JSON. Với Spring Framework 6.x, Jackson XML converter dùng `XmlMapper` từ thư viện:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

Ví dụ trên là dependency Maven đặt trong `<dependencies>`, để Spring Boot parent/BOM quản lý version. Không thêm version Jackson khác biệt ngẫu nhiên với bộ dependency đang dùng.

Một record được khai báo rõ tên root XML:

```java
@JacksonXmlRootElement(localName = "message")
record MessageDto(String text) {
}
```

Import `com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement`. Với XML converter được đăng ký, handler:

```java
@PostMapping(
        path = "/messages/xml",
        consumes = MediaType.APPLICATION_XML_VALUE,
        produces = MediaType.APPLICATION_XML_VALUE)
public MessageDto echoXml(@RequestBody MessageDto input) {
    return input;
}
```

Một request phù hợp:

```http
POST /api/messages/xml
Content-Type: application/xml
Accept: application/xml

<message><text>Chao ban</text></message>
```

Response XML có phần tử `message` và con `text` chứa `Chao ban`. Định dạng cụ thể (XML declaration, whitespace, namespace) tùy cấu hình serializer; không nên kiểm thử bằng so sánh nguyên văn mọi byte nếu hợp đồng chỉ yêu cầu cấu trúc/giá trị XML.

Spring MVC còn có những converter XML khác, ví dụ `Jaxb2RootElementHttpMessageConverter` khi JAXB phù hợp hiện diện, `MarshallingHttpMessageConverter` dựa vào Spring OXM, và `SourceHttpMessageConverter` cho kiểu `Source`. **Đừng đồng nhất** "hỗ trợ XML" với "chắc chắn đang dùng Jackson XML"; hãy kiểm tra classpath và converter list. Java 17 không còn tích hợp JAXB vào JDK như các phiên bản Java cũ; dùng JAXB phải thêm API/provider tương thích.

### 8.1. Có cần hai endpoint để trả JSON và XML?

Không nhất thiết. Nếu cùng kiểu DTO có converter cho cả hai media type và mapping cho phép:

```java
@GetMapping(
        path = "/messages/format",
        produces = {
            MediaType.APPLICATION_JSON_VALUE,
            MediaType.APPLICATION_XML_VALUE
        })
public MessageDto format() {
    return new MessageDto("Xin chào");
}
```

- `Accept: application/json` → JSON converter.
- `Accept: application/xml` → XML converter, nếu thư viện và cấu hình hiện có hỗ trợ `MessageDto`.
- `Accept: text/plain` → thường **406 Not Acceptable** vì route không hứa biểu diễn text.
- `Accept: */*` → cả hai đều có thể chấp nhận; đừng viết test mặc định rằng XML luôn được chọn. Quy tắc negotiation và thứ tự có thể ảnh hưởng.

Đối với API tích hợp bên ngoài, công bố rõ media types được hỗ trợ và thử từng đường đọc/ghi bằng integration test.

## 9. Ví dụ đầy đủ chạy được: năm kiểu body trong cùng một ứng dụng

Ví dụ này triển khai Spring Boot 3.x và Spring Framework 6.x, Java 17+, gồm:

- Response text `String`.
- Response và request `byte[]`.
- Response file `Resource`.
- JSON request/response object.
- XML request/response object (phụ thuộc Jackson XML).
- Một endpoint JSON/XML dùng header `Accept` để chọn biểu diễn.

### 9.1. Maven dependencies

Tạo dự án Spring Boot 3.x trên [Spring Initializr](https://start.spring.io/) với **Java 17+** và **Spring Web**. Nếu project đã có dependency Spring Web do Initializr tạo, giữ nguyên. Trong `pom.xml`, thêm dependency XML bên cạnh Spring Web:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-xml</artifactId>
    </dependency>
</dependencies>
```

Đây là **đoạn `<dependencies>`**, không phải file POM độc lập; Spring Initializr cung cấp `project`, `parent`/BOM, plugin Maven và metadata. Nếu đang dùng dependency management của Spring Boot, thường không cần khai báo phiên bản Jackson XML.

### 9.2. Toàn bộ source Java

Thay nội dung file `src/main/java/com/example/demo/DemoApplication.java` bằng đoạn hoàn chỉnh dưới đây. Chỉ có một `public class`; record `MessageDto` là top-level package-private hợp lệ trong cùng file:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@JacksonXmlRootElement(localName = "message")
record MessageDto(String text) {
}

@RestController
@RequestMapping("/api")
class ConverterController {

    @GetMapping(path = "/text", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> text() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/plain;charset=UTF-8"))
                .body("Xin chào Spring MVC");
    }

    @PostMapping(
            path = "/echo-text",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String echoText(@RequestBody String body) {
        return "text: " + body;
    }

    @GetMapping(
            path = "/bytes",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> bytes() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(new byte[] {65, 66, 67});
    }

    @PostMapping(
            path = "/byte-count",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String byteCount(@RequestBody byte[] data) {
        return "bytes=" + data.length;
    }

    @GetMapping(
            path = "/download",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Resource> download() {
        Resource file = new ByteArrayResource(
                "FILE\n".getBytes(StandardCharsets.UTF_8));

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"example.txt\"")
                .body(file);
    }

    @PostMapping(
            path = "/messages/json",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public MessageDto json(@RequestBody MessageDto input) {
        return input;
    }

    @PostMapping(
            path = "/messages/xml",
            consumes = MediaType.APPLICATION_XML_VALUE,
            produces = MediaType.APPLICATION_XML_VALUE)
    public MessageDto xml(@RequestBody MessageDto input) {
        return input;
    }

    @GetMapping(
            path = "/messages/format",
            produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
            })
    public MessageDto format() {
        return new MessageDto("Xin chào");
    }
}
```

**Vì sao Spring dùng đúng converter?**

- `text()` trả `ResponseEntity<String>`, nên body là String, được ghi qua converter dành cho chuỗi.
- `bytes()` trả `ResponseEntity<byte[]>`, nên body là byte array (không phải JSON list).
- `download()` trả `ResponseEntity<Resource>`, nên converter cho Resource đọc nội dung resource.
- `json()` nhận và trả `MessageDto` với `application/json`, nên converter JSON đọc/ghi.
- `xml()` nhận và trả `MessageDto` với `application/xml`, nên converter XML đọc/ghi.
- `format()` cũng trả `MessageDto`, nhưng route cho phép cả JSON lẫn XML; giá trị `Accept` là yếu tố quyết định đầu ra.

### 9.3. Chạy ứng dụng

Từ thư mục gốc dự án:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

### 9.4. Kiểm chứng request và response

**Text:**

```bash
curl -s -H 'Accept: text/plain' \
  http://localhost:8080/api/text
```

Body UTF-8:

```text
Xin chào Spring MVC
```

**Text request:**

```bash
curl -s -X POST \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'Java' \
  http://localhost:8080/api/echo-text
```

Body:

```text
text: Java
```

**Byte response:**

```bash
curl -s -o sample.bin -H 'Accept: application/octet-stream' \
  http://localhost:8080/api/bytes
xxd -p sample.bin
```

Nếu máy có `xxd`, dòng in ra là:

```text
414243
```

Đây là **mã hex của ba byte**; cURL tự lưu body nhị phân vào `sample.bin`, không có ký tự newline thừa. Không phải output JSON `[65,66,67]`.

**Byte request:**

```bash
curl -s -X POST \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'ABC' \
  http://localhost:8080/api/byte-count
```

Body:

```text
bytes=3
```

**Resource download:**

```bash
curl -s -OJ http://localhost:8080/api/download
```

Với client cURL hỗ trợ `-OJ`/Content-Disposition, file được lưu tên `example.txt` (trừ khi môi trường hoặc tên file xung đột dẫn đến cách xử lý khác). Nội dung là `FILE` và newline cuối, tổng **5 byte**. Nếu không muốn client tự chọn tên từ header, dùng `curl -s -o local.txt URL` để lưu vào file mong muốn.

**JSON input và output:**

```bash
curl -s -X POST http://localhost:8080/api/messages/json \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"text":"Chao ban"}'
```

Body JSON về mặt dữ liệu:

```json
{"text":"Chao ban"}
```

**XML input và output:**

```bash
curl -s -X POST http://localhost:8080/api/messages/xml \
  -H 'Content-Type: application/xml' \
  -H 'Accept: application/xml' \
  --data-binary '<message><text>Chao ban</text></message>'
```

Body XML có giá trị tương đương:

```xml
<message><text>Chao ban</text></message>
```

Jackson XML có thể phát ra XML declaration hoặc định dạng khác tương đương; ví dụ trên trình bày **cấu trúc và giá trị**, không cam kết byte-for-byte trừ khi serializer được cấu hình cố định.

**Negotiation theo `Accept`:**

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/messages/format

curl -i -H 'Accept: application/xml' \
  http://localhost:8080/api/messages/format

curl -i -H 'Accept: text/plain' \
  http://localhost:8080/api/messages/format
```

Hai request đầu nhận `200 OK` với `Content-Type` tương ứng JSON/XML, còn request thứ ba thường nhận **406 Not Acceptable** do mapping chỉ cho phép JSON/XML. Nếu muốn so sánh kết quả trên Windows PowerShell, dùng `curl.exe` và viết mỗi lệnh trên một dòng để tránh cú pháp nối dòng của shell Bash.

## 10. Khi converter được chọn sai hoặc không tìm thấy

### 10.1. `406 Not Acceptable`: client không chấp nhận kiểu server có thể tạo

Ví dụ:

```http
GET /api/messages/format
Accept: text/plain
```

Trong demo, route chỉ có `produces = application/json, application/xml`. Kết quả thường 406. Cách xử lý là client yêu cầu một biểu diễn thực sự được hỗ trợ, hoặc server chủ động triển khai thêm biểu diễn (kèm converter/mapping tương ứng). Không nên cố ép `Content-Type` sai để né lỗi.

### 10.2. `415 Unsupported Media Type`: request body không được hỗ trợ

Ví dụ:

```http
POST /api/messages/json
Content-Type: application/xml

<message><text>Hi</text></message>
```

Mapping chỉ `consumes = application/json`; request có thể bị từ chối 415 **trước khi đọc body**. Cũng có thể phát sinh 415 khi không có converter đọc được body vào kiểu tham số cần thiết với media type đã khai báo.

### 10.3. `400 Bad Request`: payload sai nội dung

```http
POST /api/messages/json
Content-Type: application/json

{"text":
```

Header đúng JSON nhưng body sai cú pháp. Jackson không parse được và Spring MVC thường trả 400. Lỗi parse, lỗi kiểu field, lỗi validation và lỗi nội dung nghiệp vụ là những nhóm khác nhau; nên có xử lý lỗi nhất quán thay vì đổi media type để lấp lỗi.

### 10.4. `500 Internal Server Error` hoặc lỗi ghi response

Ngay cả khi route và `Accept` tương thích, server vẫn có thể lỗi khi serialize object, ví dụ vòng tham chiếu, getter ném exception, serializer thiếu cấu hình hoặc đối tượng không thể biểu diễn bằng converter hiện có. Để chẩn đoán, xem class converter thực dùng, stacktrace gốc và kiểu Java trả về. Đừng mặc định mọi lỗi response là 406; 406 chủ yếu nói về **không thể thỏa định dạng client chấp nhận**.

### 10.5. Tại sao `return "index";` đôi khi trả view, đôi khi trả text?

```java
@Controller
class PageController {
    @GetMapping("/page")
    public String page() {
        return "index";
    }
}
```

Trong `@Controller`, `String` có thể là **tên view**. Khi method có `@ResponseBody` hoặc class dùng `@RestController`, String trở thành **HTTP body** và converter có cơ hội xử lý nó. Đây là khác biệt ở tầng return-value handler, không phải lỗi của String converter.

## 11. Cấu hình converter trong Spring MVC và Spring Boot

### 11.1. Thông thường, không cần đăng ký thủ công

Spring Web MVC đăng ký một bộ converter mặc định tùy thuộc các thư viện hiện diện. Spring Boot còn tự động thêm/chỉnh một số converter theo dependency và cấu hình riêng. Với ứng dụng dùng `spring-boot-starter-web` và Jackson, `@RestController` trả DTO thường đã có JSON. Thêm Jackson XML tương thích thường cho phép XML nếu không có cấu hình khác chặn.

Kiểm tra dependency quan trọng hơn viết bean converter mới chỉ để sửa `406`. Khi cả JSON/XML cùng hỗ trợ và client không gửi `Accept` cụ thể, việc ứng dụng chọn định dạng nào còn tùy thứ tự converter và chính sách negotiation.

### 11.2. `extendMessageConverters` so với `configureMessageConverters`

Trong Spring Framework **6.x**:

```java
@Configuration
class ConverterConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Quan sát hoặc tùy chỉnh danh sách đã được MVC cấu hình.
        // Không tự xóa converter mặc định khi chưa có lý do.
    }
}
```

Đoạn trên là **config minh họa**, cần import `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, `org.springframework.http.converter.HttpMessageConverter` và `java.util.List`. `extendMessageConverters` cho phép điều chỉnh danh sách sau bước cấu hình mặc định.

Còn `configureMessageConverters(List<...>)` trong Spring MVC 6.x có thể **thay thế cơ chế đăng ký converter mặc định** nếu tự đưa vào các converter; với Spring Boot có thêm các cơ chế tự động đăng ký bean cần xem xét. Đừng thêm mỗi JSON converter rồi làm mất support String, Resource hoặc các converter trước đó. Cũng không tự thêm `@EnableWebMvc` trong Boot nếu không chủ đích nhận trách nhiệm về MVC configuration.

Nếu chỉ cần định dạng cụ thể cho một endpoint, nên khai báo `consumes`/`produces`, dùng `ResponseEntity` và kiểu body chính xác trước khi đụng vào danh sách converter toàn ứng dụng.

### 11.3. Xem thứ tự converter đang chạy

Trong ứng dụng Boot 3.x / Framework 6.x, có thể quan sát danh sách converter được MVC cấu hình:

```java
// Đoạn chẩn đoán riêng; không bắt buộc thêm vào demo.
@Component
class ConverterPrinter implements ApplicationRunner {

    private final RequestMappingHandlerAdapter adapter;

    ConverterPrinter(RequestMappingHandlerAdapter adapter) {
        this.adapter = adapter;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (HttpMessageConverter<?> converter
                : adapter.getMessageConverters()) {
            System.out.println(converter.getClass().getSimpleName());
        }
    }
}
```

Đoạn này cần import `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationRunner`, `org.springframework.boot.ApplicationArguments`, `org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter` và `org.springframework.http.converter.HttpMessageConverter`; đây là **mã chẩn đoán**, không phải test cố định về output hay thứ tự danh sách. Tên và số lượng converter phụ thuộc version và classpath.

Nếu các media types được cấu hình quá rộng cho custom converter, nó có thể được chọn trước converter hợp lý hơn. Cần kiểm thử `Accept: */*`, `Accept: application/json` và `Accept: application/xml` sau khi thay đổi thứ tự.

## 12. Cách chọn dựa trên yêu cầu ứng dụng

| Yêu cầu đầu ra | Java return type đề xuất | Media type | Lý do |
| --- | --- | --- | --- |
| Thông báo text đơn giản | `String` | `text/plain;charset=UTF-8` | Rõ dạng văn bản |
| Dữ liệu CSV nhỏ tự dựng | `String` / `byte[]` | `text/csv` | Chọn encoding và escape CSV đúng |
| Binary nhỏ có sẵn trong RAM | `byte[]` | `application/octet-stream` hoặc type cụ thể | Gửi trực tiếp byte |
| File trên đĩa/tài nguyên có thể mở stream | `Resource` | Type thật, với `Content-Disposition` khi tải xuống | Không cần giữ toàn bộ nội dung file trong một mảng |
| REST payload có schema | DTO/record | `application/json` | Jackson mapping và JSON escaping |
| Tích hợp XML theo hợp đồng | DTO/record có XML mapping phù hợp | `application/xml` | Jackson XML/JAXB tương thích |
| Cùng một object hỗ trợ JSON/XML | DTO/record | `produces={JSON,XML}` | Chọn biểu diễn qua `Accept` |

Không dùng `String`/`byte[]` chỉ để né thiết kế DTO. Không dùng `Resource` thay JSON cho object có schema. Converter biến dữ liệu **trên đường truyền**, không thay thế validation, authentication/authorization, mã hóa dữ liệu nhạy cảm, hay kiểm soát kích thước request.

## 13. Các rủi ro và lỗi phổ biến khi đưa vào production

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nhầm request `Content-Type` với `Accept` | 415 hoặc 406 | Chỉ rõ chiều đọc/gửi body |
| Trả `String` trông giống JSON | Có thể trả text không hợp lệ hoặc không đúng serializer | Trả DTO qua Jackson |
| Gửi object JSON nhưng ép `produces=text/plain` | Converter không phù hợp hoặc sai contract | Sử dụng `application/json` |
| Tưởng `byte[]` là Base64 JSON | Client parse sai | Phân biệt binary raw với JSON Base64 |
| Đọc cả file lớn vào byte array | Tốn RAM, khó scale | `Resource`/streaming phù hợp |
| Giả định XML luôn có | 406, 500 hoặc thiếu converter | Thêm XML dependency và test classpath |
| Tùy biến converter quá rộng `*/*` | Lấn converter mặc định | Hạn chế supportedMediaTypes và kiểm soát thứ tự |
| Bỏ converter mặc định khi override config | String/Resource/JSON ngừng hoạt động | Ưu tiên cách mở rộng an toàn |
| Trả Resource chứa path do client tự chọn | Lộ file, path traversal | Xác thực quyền và giới hạn đường dẫn |
| Deserialize object JSON/XML vào entity chứa quyền | Mass assignment, lộ field | Request DTO, validate, explicit mapping |
| Tin tuyệt đối filename/media type từ client | File giả định dạng, injection | Validate dữ liệu, sanitize filename |
| XML parser cho phép external entities | XXE, đọc tài nguyên ngoài ý muốn | Dùng thư viện XML đã cập nhật và cấu hình bảo vệ parser |

Đặc biệt với XML, nếu thêm custom parser hoặc converter mới, kiểm tra **XXE / external entity resolution**, giới hạn kích thước và độ sâu tài liệu. Không chủ động bật external entities để xử lý dữ liệu không tin cậy. Với JSON, chú ý độ sâu nesting, kích thước request và những field không được phép deserialze vào domain entity.

### 13.1. Trình tự gỡ lỗi nhanh

1. Xem method có `@ResponseBody`/`@RestController` hoặc trả `ResponseEntity` không.
2. Ghi lại **runtime body type** và loại tham số `@RequestBody`.
3. Kiểm tra request `Content-Type`, `Accept` và mapping `consumes`/`produces`.
4. Xác nhận dependency converter tương ứng có trong runtime classpath.
5. Kiểm tra danh sách converter + thứ tự nếu có custom config.
6. Dùng `curl -i` hoặc integration test để đọc status, response `Content-Type` và body thực.
7. Nếu là 400/500, xem exception gốc của converter; đừng nhầm lỗi dữ liệu với lỗi negotiation.

## 14. Tự kiểm tra

**Câu 1.** Client gửi `POST /messages/json` với `Content-Type: application/xml` nhưng mapping chỉ `consumes=application/json`. Trả gì?

**Đáp án:** Thông thường **415 Unsupported Media Type**, vì định dạng request body không khớp.

**Câu 2.** Một endpoint trả `ResponseEntity<byte[]>` ba byte `65,66,67`, media type `application/octet-stream`. Client nhận gì?

**Đáp án:** Ba byte `41 42 43` theo hệ hex (ASCII `ABC`), không phải JSON array hay Base64.

**Câu 3.** Một endpoint trả `MessageDto` và hỗ trợ JSON, XML. Client gửi `Accept: application/xml` nhưng app chưa có converter XML. Có tự đổi JSON thành XML không?

**Đáp án:** Không. Cần converter XML phù hợp trên classpath và hỗ trợ kiểu Java tương ứng; nếu không, response không thể thỏa contract XML.

**Câu 4.** Vì sao `return "{\"text\":\"hi\"}";` là cách không nên dùng cho JSON API?

**Đáp án:** Đây là String thủ công, có nguy cơ escape không đúng, sai content type và lệ thuộc converter selection; hãy trả DTO/record để Jackson serialize.

**Câu 5.** Tại sao `Resource` thường hữu ích hơn `byte[]` với file dung lượng lớn?

**Đáp án:** Resource có thể đại diện cho nguồn dữ liệu được đọc khi gửi response, thay vì nạp toàn bộ file vào mảng byte trước đó; vẫn phải chọn loại Resource và cấu hình streaming phù hợp.

**Câu 6.** `@GetMapping(produces=APPLICATION_JSON_VALUE)` có bảo đảm bất kỳ `String` trả về nào là JSON hợp lệ?

**Đáp án:** Không. `produces` là contract media type của mapping, không thay thế việc serialize object bằng JSON converter hay validate JSON thô.

## 15. Tài liệu chuẩn

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): các converter cơ bản, JSON/XML và dependency cần có.
- [Spring Framework 6.2 — Configuring Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): `configureMessageConverters` và `extendMessageConverters`.
- [Spring Framework — Request Mapping: consumes/produces](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): mapping dựa trên Content-Type/Accept.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): status, headers và body converter.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): giải mã request body và validation.
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): chuyển return value thành HTTP response body.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): converter auto-configuration trong Boot 3.x.
- [Spring Framework — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html): cơ chế partial content cho Resource trong những điều kiện thích hợp.

**Tổng kết ứng dụng:** Bắt đầu từ **kiểu Java của body** và **media type mà HTTP request/response yêu cầu**, sau đó để converter đúng trách nhiệm đọc hoặc ghi. Dùng `String` cho text, `byte[]` cho binary ở bộ nhớ, `Resource` cho nguồn tài nguyên, DTO/record + Jackson cho JSON, và converter/XML mapping tương thích cho XML. Kiểm tra đồng thời `Content-Type`, `Accept`, `consumes`, `produces`, thư viện runtime và thứ tự converter trước khi tùy chỉnh cấu hình MVC.
