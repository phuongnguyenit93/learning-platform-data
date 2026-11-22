# Thương lượng nội dung theo Accept và lựa chọn media type trong Spring MVC

## 1. Mục tiêu và ngữ cảnh

Một tài nguyên HTTP có thể có **nhiều cách biểu diễn (representations)**: JSON cho ứng dụng, văn bản thuần cho công cụ dòng lệnh, HTML cho trình duyệt, XML cho hệ thống tích hợp. **Content negotiation** là quá trình xác định representation nào phù hợp với khả năng và ưu tiên mà client nêu ra, khả năng của server, mapping controller và bộ chuyển đổi nội dung.

Trong Spring MVC (Servlet stack), bài này giúp bạn:

- Đọc chính xác header `Accept`, media type, wildcard, trọng số `q` và quan hệ với `Content-Type`.
- Biết `ContentNegotiationManager` xác định media type client mong muốn ra sao; hiểu mặc định hiện đại và các chiến lược tùy chỉnh.
- Giải thích `@GetMapping(produces=...)`, `@RequestMapping(produces=...)`, `@ResponseBody`/`@RestController` và `HttpMessageConverter` cùng tham gia chọn representation.
- Biết khi nào xảy ra `406 Not Acceptable`, phân biệt với `415 Unsupported Media Type` và các lỗi khác.
- Thiết kế endpoint hỗ trợ một hay nhiều representation, kiểm tra bằng `curl`/MockMvc, lưu ý cache `Vary: Accept`, versioning và bảo mật.

Ví dụ dùng **Java 17+ với Spring Framework 6.2/Spring Boot 3.x** (và dependency Spring MVC + Jackson); không áp các giả định của Spring WebFlux. Các đoạn lệnh/tests nêu hành vi kỳ vọng với ứng dụng mẫu, không khẳng định output/body lỗi HTTP cố định trên mọi server hoặc cấu hình bảo mật.

## 2. Phân biệt resource, representation và media type

**Resource** là đối tượng được xác định bởi URI, chẳng hạn `/api/media/items/7`. Cùng resource có thể được trình bày thành những representation khác nhau, ví dụ:

```http
GET /api/media/items/7 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Server có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"Pen"}
```

Trong khi client khác yêu cầu văn bản:

```http
GET /api/media/items/7 HTTP/1.1
Host: localhost:8080
Accept: text/plain
```

Server có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

Item 7: Pen
```

Đây là **một URL, hai representation**, với điều kiện server thật sự hỗ trợ cả hai. Header `Content-Type` ở response xác nhận **kiểu dữ liệu thực được gửi**, còn `Accept` ở request nêu **định dạng client muốn nhận**. Giá trị `charset` và một số header khác phụ thuộc converter/cấu hình; các mẫu HTTP ở đây minh họa, không cam kết byte-for-byte.

Media type có cú pháp `type/subtype`, có thể mang parameters:

- `application/json`: JSON.
- `text/plain`: văn bản thuần.
- `text/html`: HTML.
- `application/xml`: XML.
- `application/problem+json`: dạng Problem Details theo JSON.
- `application/vnd.example.v1+json`: kiểu JSON đặc thù ứng dụng (vendor media type).
- `text/plain;charset=UTF-8`: loại nội dung có tham số charset.

**Không phải cứ trả về object Java thì server tự tạo được XML/CSV/HTML.** Phải có cơ chế serialize representation đó, được cấu hình và thỏa điều kiện media type.

## 3. Ngữ nghĩa của Accept

`Accept` cho server biết những media type mà client chấp nhận trong **response**. Đây là header cho *response representation*, không mô tả request body. Dạng tổng quát:

```http
Accept: application/json, text/plain;q=0.6, */*;q=0.1
```

Theo HTTP Semantics (RFC 9110):

- **Thiếu `Accept`:** client không hạn chế server vào một danh sách media type cụ thể; server có thể chọn representation khả dụng. HTTP không quy định “bắt buộc phải là JSON”.
- **`Accept: */*`:** cho phép bất kỳ media type nào. Không nói client *ưu tiên* JSON.
- **`Accept: application/*`:** cho phép các subtype trong nhóm `application` (chẳng hạn `application/json`), nếu server hỗ trợ.
- **`Accept: application/json`:** chỉ chỉ rõ JSON; nếu server chỉ có `text/plain`, phía Spring MVC thường dẫn đến HTTP 406.
- **`Accept: application/json, text/plain`:** cả hai có trọng số mặc định `q=1`; chỉ riêng header này không ấn định representation được chọn khi hai bản đều đáp ứng.
- **`q`:** trọng số ưu tiên nằm trong khoảng `0` đến `1`; nếu bỏ qua thì mặc định `1`; `q=0` nghĩa là representation đó không được chấp nhận.
- **Wildcard:** `*/*` bao quát mọi loại, `text/*` bao quát subtype thuộc nhóm text. Media range càng cụ thể thường có độ ưu tiên tương ứng khi xác định q cho media type cụ thể.

Ví dụ:

```http
Accept: application/json;q=0.9, text/plain;q=0.4
```

Nếu JSON và text đều có thể phục vụ, JSON được **ưu tiên hơn theo q**. Đổi q thành `application/json;q=0.2, text/plain;q=0.9` thể hiện ưu tiên text. `q` là **trọng số tương đối**, không phải xác suất 90% server trả JSON.

Ví dụ thêm:

```http
Accept: application/json;q=0, text/plain;q=1
```

Theo ngữ nghĩa HTTP, client đã loại trừ JSON và chấp nhận text. Điều này chỉ có nghĩa khi server thật sự có representation text; nếu không có, server có thể trả 406 hoặc theo HTTP specification lựa chọn bỏ qua preference. Trong ứng dụng Spring MVC có `produces` rõ ràng, trường hợp không tương thích thường là 406.

Một tình huống cần tránh suy luận sai:

```http
Accept: application/json;q=0, */*;q=0.8
```

**Wildcard không nhất thiết “cứu” JSON đã bị loại trừ:** media range cụ thể `application/json` có quyền ưu tiên khi xác định q cho chính JSON đó. Việc tính mức chấp nhận dựa trên độ đặc hiệu và q chứ không chỉ lấy giá trị q lớn nhất trong toàn bộ header.

### Bảng đọc nhanh

| Accept | Ý định ở HTTP | Khi endpoint chỉ trả JSON |
| --- | --- | --- |
| Không có header | Không chỉ định hạn chế | Thường JSON, nếu framework chọn được |
| `*/*` | Chấp nhận tất cả | Thường JSON |
| `application/json` | Muốn JSON | JSON (nếu converter ghi được) |
| `application/*` | Chấp nhận họ application | JSON có thể phù hợp |
| `text/plain` | Chỉ muốn text | Thường 406 |
| `application/xml` | Chỉ muốn XML | Thường 406 |
| `application/json;q=0` | Không nhận JSON | Thường 406 nếu không có bản hợp lệ khác |
| `application/json;q=0.2,text/plain;q=0.9` | Ưu tiên text hơn JSON | Ứng dụng chỉ có JSON vẫn có thể trả JSON vì q=0.2 vẫn chấp nhận |

Đây là **mô hình HTTP và kết quả thường gặp**; mapping, codec và interceptor cụ thể mới quyết định status cuối cùng của ứng dụng.

## 4. Accept và Content-Type: hai chiều dữ liệu

Bốn tình huống:

| Header | Hướng | Câu hỏi |
| --- | --- | --- |
| Request `Accept` | Client → Server | “Tôi muốn nhận response ở định dạng nào?” |
| Request `Content-Type` | Client → Server | “Body tôi **đang gửi** ở định dạng nào?” |
| Response `Content-Type` | Server → Client | “Body server **đang trả** có định dạng nào?” |
| Response `Vary` | Server → client/cache | “Biến thể response bị ảnh hưởng bởi header request nào?” |

Một POST có thể đồng thời gửi:

```http
POST /api/media/echo HTTP/1.1
Content-Type: application/json
Accept: application/json

{"id":7,"name":"Pen"}
```

- `Content-Type: application/json` xác định cách server **đọc** body. Trong Spring MVC, `consumes` và `HttpMessageConverter.canRead` liên quan chiều này.
- `Accept: application/json` ảnh hưởng cách server **ghi** response. Trong Spring MVC, `produces` và `HttpMessageConverter.canWrite` liên quan chiều này.
- Nếu body bị gắn nhãn `text/plain` nhưng endpoint chỉ nhận JSON → thường **415 Unsupported Media Type**.
- Nếu body gửi JSON đúng nhưng client yêu cầu XML cho response, endpoint chỉ trả JSON → thường **406 Not Acceptable**.
- Nếu JSON cú pháp sai nhưng `Content-Type` đúng, lỗi thường **400 Bad Request** vì không đọc/deserialize được body. Không nhầm 400 với 406 hay 415.

`Accept-Language` chọn ngôn ngữ, `Accept-Encoding` chọn content coding như gzip, còn `Accept` ở đây chọn **media type**. Các header này là những chiều negotiation khác nhau, không thay thế nhau. CORS `Access-Control-Allow-Headers`/`Access-Control-Allow-Methods` cũng là vấn đề riêng.

## 5. Spring MVC tìm media type và chọn representation thế nào?

Luồng tổng quan, có thể xem như hai quyết định liên quan:

```text
HTTP request: path + method + Accept + (Content-Type nếu có body)
            |
            v
ContentNegotiationManager
  -> xác định requested/acceptable media types
            |
            v
RequestMappingHandlerMapping
  -> chọn handler khớp path, HTTP method, params/headers,
     consumes (request body) và produces (response)
            |
            v
Handler return value: object / String / ResponseEntity / ...
            |
            v
RequestResponseBodyMethodProcessor hoặc HTTP entity processor
  -> so acceptable media types với các kiểu có thể ghi
     bởi HttpMessageConverter tương ứng return type
            |
            v
Chọn response media type + converter -> serialize body
            |
            v
HTTP response: status + Content-Type + body
```

**Đây là sơ đồ logic, không phải một thứ tự cứng cho mọi nhánh nội bộ.** Handler mapping nhận thông tin về `Accept` từ negotiation manager khi đánh giá điều kiện `produces`; khi chuẩn bị ghi response, Spring tiếp tục dùng thông tin acceptable/producible media types cùng tập converter. Một handler có thể match về path/method nhưng sau đó vẫn không ghi được kiểu body như mong muốn.

### 5.1. Mặc định content negotiation trong Spring MVC hiện đại

Với Spring MVC 6.x không tùy chỉnh, **header `Accept` là nguồn được kiểm tra theo mặc định** để xác định requested media types. Đừng sao chép mô hình Spring MVC 4.x cũ, nơi path extension như `.json` từng được ưu tiên trong cấu hình lịch sử.

Trong ứng dụng 6.x phổ biến:

- `GET /api/items/7` và `GET /api/items/7.json` **không mặc nhiên là cùng một route**. Việc match suffix/path extension phụ thuộc cấu hình routing và không phải cơ chế mặc định nên dựa vào.
- Query `?format=json` **không mặc nhiên điều khiển** content negotiation. Muốn dùng cần cấu hình strategy rõ ràng.
- Không có `Accept` hoặc client gửi `*/*`: Spring có thể chọn một kiểu server hỗ trợ, nhưng nếu bạn tự khai báo nhiều handler cùng path khác `produces` và không định nghĩa ưu tiên mặc định, **đừng giả định lựa chọn luôn ổn định**. Nên thiết kế representation mặc định tường minh khi hợp đồng API cần nó.
- Bộ lọc, error handler, controller advice, Spring Security và reverse proxy có thể làm status/header quan sát được khác ví dụ.

### 5.2. `@RequestMapping(produces=...)` là điều kiện mapping

```java
@GetMapping(path = "/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Book book(@PathVariable long id) {
    return new Book(id, "Java");
}
```

`produces` mô tả loại response mà method **cam kết có thể cung cấp** cho điều kiện chọn handler. Header `Accept: application/json` tương thích; `Accept: application/xml` không tương thích khi chỉ có handler JSON.

Ghi chú:

- Method-level `produces` có thể **override** declaration ở class level thay vì “thêm vào” danh sách của class.
- Một method có thể khai báo `produces = {"application/json", "application/xml"}`, **nhưng chỉ khai báo không tạo khả năng xuất XML**. Phải có converter và serializer hỗ trợ cùng kiểu object.
- Dùng `produces` khi API cam kết response media type ổn định, muốn client nhận 406 khi yêu cầu định dạng không hỗ trợ.
- Nếu dùng `@Controller` thường và return `String` là **tên view**, cần `@ResponseBody` để serialize giá trị; với `@RestController`, behavior tương đương `@Controller + @ResponseBody` cho method.
- `produces` thường được xét ngay khi chọn method; converter thực tế được kiểm tra ở giai đoạn ghi response. Hai điểm này nên được debug riêng.

### 5.3. `HttpMessageConverter` quyết định ghi được kiểu nào

Spring MVC ghi body từ `@ResponseBody`/`ResponseEntity` thông qua các converter:

| Converter (khái niệm) | Dữ liệu/định dạng thường ghi |
| --- | --- |
| `MappingJackson2HttpMessageConverter` | Java object → JSON qua Jackson ObjectMapper |
| `StringHttpMessageConverter` | `String` → text; mặc định hỗ trợ các text media type và có thể cấu hình khác |
| `ByteArrayHttpMessageConverter` | `byte[]` → byte stream |
| `MappingJackson2XmlHttpMessageConverter` hoặc converter XML khác | Java object → XML nếu có đúng thư viện và đăng ký |
| `FormHttpMessageConverter` | Form/`MultiValueMap` theo media type được hỗ trợ |

Tên/lựa chọn converter có thể thay đổi với phiên bản và cấu hình Spring; ví dụ `StringHttpMessageConverter` có thể hỗ trợ nhiều media type và lựa chọn converter chịu ảnh hưởng thứ tự. **Không suy ra JSON từ một `String`** chỉ vì client gửi `Accept: application/json`; để có JSON hợp lệ, hãy trả một DTO/record phù hợp và dùng JSON converter.

Nếu không có converter ghi được return type với media type cần thiết, Spring không thể thực hiện content negotiation như mong muốn. Khác biệt giữa “mapping từ chối `produces`” và “converter không ghi được” quan trọng khi đọc log.

### 5.4. Chọn media type là giao của ba yếu tố

Cách suy nghĩ hữu ích:

1. **Client chấp nhận** (`Accept` + q + wildcard).
2. **Handler công bố được cung cấp** (`produces` hoặc khả năng suy ra nếu không khai báo).
3. **Converter thật sự hỗ trợ** Java return type và media type đích.

Một lựa chọn hợp lệ phải thỏa điều kiện của các tầng liên quan. Chỉ thêm `produces="application/xml"` không đủ nếu thiếu XML converter. Chỉ thêm Jackson vào classpath cũng không đảm bảo client muốn XML được phục vụ. Tăng q của một media type không “tạo ra” representation mà server chưa hỗ trợ.

## 6. Ví dụ Java 17+ Spring Boot: một URL, hai representation

Mục tiêu là minh họa hai method xử lý **cùng URL** nhưng khác `produces`. Khi `Accept` rõ ràng, Spring MVC chọn method tương ứng.

Tạo một dự án Maven Spring Boot 3.x, Java 17+ với `spring-boot-starter-web` (thường bao gồm Jackson JSON). Đặt hai tệp sau cùng package `com.example.demo`.

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/demo/MediaController.java`:

```java
package com.example.demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/media")
public class MediaController {

    @GetMapping(path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Item itemJson(@PathVariable("id") long id) {
        return new Item(id, "Pen");
    }

    @GetMapping(path = "/items/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String itemText(@PathVariable("id") long id) {
        return "Item " + id + ": Pen";
    }

    @GetMapping(path = "/json-only/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Item jsonOnly(@PathVariable("id") long id) {
        return new Item(id, "Pen");
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Item echo(@RequestBody Item item) {
        return item;
    }

    public record Item(long id, String name) {}
}
```

Điểm quan trọng:

- `GET /api/media/items/7` + `Accept: application/json` → handler `itemJson`, object Java được Jackson serialize JSON.
- Cùng URL + `Accept: text/plain` → handler `itemText`, String được text converter ghi ra.
- `GET /api/media/json-only/7` + `Accept: text/plain` → không có handler representation phù hợp, thường 406.
- `POST /api/media/echo` dùng `consumes` cho body **đến**, `produces` cho body **đi**.
- Handler `itemJson` và `itemText` có cùng URL và GET nhưng khác `produces`, vì vậy đều có thể được đăng ký. **Đừng dựa vào behavior khi `Accept` không nêu ưu tiên rõ ràng**: hai mapping có thể có mức ưu tiên tương đương và kết quả tùy logic so khớp/cấu hình. Một API production thường cần chọn một định dạng mặc định hợp đồng và thiết kế fallback rõ ràng.
- Ví dụ không có database; bất kể `id` nhận gì, resource minh họa đều có tên `Pen`. Trong dịch vụ thật, “không có resource” là 404 nghiệp vụ riêng, không phải lỗi content negotiation.

Chạy trong dự án Maven Boot đã cấu hình:

```bash
./mvnw spring-boot:run
```

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Boot mặc định dùng cổng 8080 nếu bạn chưa đổi `server.port`. Không thể dùng `javac MediaController.java` độc lập khi không có Spring/Boot/Jackson dependencies trên classpath.

## 7. Thử bằng curl và dự đoán status/Content-Type

Trong ví dụ dưới, `curl -i` hiển thị status và headers. Trên Windows PowerShell (đặc biệt phiên bản cũ), ưu tiên `curl.exe`; dấu `\` nối dòng là cú pháp bash/zsh, có thể viết mỗi command trên một dòng nếu dùng PowerShell.

### 7.1. Yêu cầu JSON

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/media/items/7
```

Kỳ vọng **200 OK**, `Content-Type` tương thích `application/json`, body:

```json
{"id":7,"name":"Pen"}
```

Không nên assert thứ tự field JSON khi serializer có thể cấu hình lại.

### 7.2. Yêu cầu text/plain

```bash
curl -i -H "Accept: text/plain" \
  http://localhost:8080/api/media/items/7
```

Kỳ vọng **200 OK**, `Content-Type` tương thích `text/plain`, body chính xác:

```text
Item 7: Pen
```

### 7.3. q-value ưu tiên text

```bash
curl -i -H "Accept: application/json;q=0.2, text/plain;q=0.9" \
  http://localhost:8080/api/media/items/7
```

Với hai handler `produces` và cấu hình MVC chuẩn, trọng số của text lớn hơn nên representation văn bản được ưu tiên. Đảo trọng số để quan sát JSON được ưu tiên:

```bash
curl -i -H "Accept: application/json;q=0.9, text/plain;q=0.2" \
  http://localhost:8080/api/media/items/7
```

Không được suy luận rằng q=0.2 “cấm” JSON: bất kỳ q dương nào vẫn biểu diễn mức chấp nhận, dù kém ưu tiên.

### 7.4. Wildcard

```bash
curl -i -H "Accept: text/*" \
  http://localhost:8080/api/media/items/7
```

Trong ví dụ, `text/plain` tương thích `text/*`, do đó client có thể nhận văn bản. Thử `Accept: */*` hoặc bỏ hẳn Accept có thể khớp nhiều representation; nếu thiết kế API cần kết quả chắc chắn, đừng kiểm thử theo một mặc định không được cam kết.

### 7.5. 406 khi không có representation thích hợp

```bash
curl -i -H "Accept: application/xml" \
  http://localhost:8080/api/media/json-only/7
```

Kỳ vọng **406 Not Acceptable**. `GET /api/media/json-only/7` có mapping GET tồn tại, nhưng `produces=application/json` không đáp ứng `application/xml`. Không cần đổi route hay HTTP method. Sửa ở client: nhận JSON; hoặc mở rộng server để thực sự hỗ trợ XML nếu hợp đồng yêu cầu.

Để xem request chỉ có một representation nhưng client ưu tiên format khác chưa hẳn thất bại, thử:

```bash
curl -i -H "Accept: application/json;q=0.2, application/xml;q=0.9" \
  http://localhost:8080/api/media/json-only/7
```

JSON **vẫn được chấp nhận** (q=0.2 > 0), nên endpoint JSON có thể đáp ứng. Server không bắt buộc phải xuất XML chỉ vì XML có q cao hơn nếu không hỗ trợ XML.

### 7.6. 415 là lỗi hướng ngược lại

```bash
curl -i -X POST http://localhost:8080/api/media/echo \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data "hello"
```

Kỳ vọng **415 Unsupported Media Type** vì `consumes=application/json`, trong khi request body được khai báo `text/plain`. Đặt `Accept: application/json` không chữa được 415 vì Accept chỉ nêu format **response**.

POST đúng:

```bash
curl -i http://localhost:8080/api/media/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"id":7,"name":"Pen"}'
```

Kỳ vọng **200 OK** và object JSON giống body gửi lên (demo echo).

POST body JSON hợp lệ nhưng muốn response XML:

```bash
curl -i http://localhost:8080/api/media/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/xml" \
  --data '{"id":7,"name":"Pen"}'
```

Thường **406** vì endpoint chỉ khai báo JSON output; JSON input vẫn là hợp lệ. Tùy cấu hình, giai đoạn từ chối có thể xảy ra trong request mapping trước khi controller được gọi.

## 8. MockMvc: kiểm tra behavior theo hợp đồng

Tạo `src/test/java/com/example/demo/MediaControllerTest.java` trong dự án có `spring-boot-starter-test`, cùng package:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(MediaController.class)
class MediaControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsJsonRepresentation() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void acceptsPlainTextRepresentation() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_PLAIN))
            .andExpect(content().string("Item 7: Pen"));
    }

    @Test
    void usesRequestedQualityPreference() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .header("Accept",
                        "text/plain;q=0.9, application/json;q=0.2"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_PLAIN));
    }

    @Test
    void acceptsTextWildcard() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .accept(MediaType.parseMediaType("text/*")))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_PLAIN));
    }

    @Test
    void returns406ForUnsupportedResponseType() throws Exception {
        mvc.perform(get("/api/media/json-only/7")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void returns415ForUnsupportedRequestBodyType() throws Exception {
        mvc.perform(post("/api/media/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void handlesValidJsonPost() throws Exception {
        mvc.perform(post("/api/media/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"id\":7,\"name\":\"Pen\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Pen"));
    }
}
```

Chạy:

```bash
./mvnw test
```

PowerShell: `.\mvnw.cmd test`. Đây là **mẫu kiểm thử có thể chạy trong ứng dụng Boot đủ dependency**, không phải tuyên bố một lệnh đã được thực thi. Nếu dự án tích hợp Spring Security, custom advice, custom converter hoặc `@WebMvcTest` được tùy chỉnh, hãy cấu hình test tương ứng trước khi diễn giải status.

Để test sát HTTP contract, hãy kiểm tra **status, Content-Type tương thích, body phù hợp** và khi cần các response header đặc biệt. Không test `Content-Type` bằng một chuỗi cố định chứa charset nếu framework được phép thêm hoặc bỏ tham số charset. Không gắn với thứ tự các field JSON.

## 9. Cấu hình ContentNegotiationManager khi thực sự cần

Spring MVC cung cấp `WebMvcConfigurer.configureContentNegotiation` để cấu hình chiến lược. Mặc định hiện đại thường chỉ dùng `Accept`. Nếu có yêu cầu hỗ trợ `?format=json` hoặc `?format=txt`, bạn có thể bật **query parameter strategy** một cách chủ động.

Ví dụ cấu hình (lớp độc lập trong cùng package ứng dụng, nhưng chỉ áp dụng khi sản phẩm **thật sự muốn** dùng tham số `format`):

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.config.annotation.ContentNegotiationConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MediaNegotiationConfig implements WebMvcConfigurer {

    @Override
    public void configureContentNegotiation(
            ContentNegotiationConfigurer configurer) {
        configurer
            .favorParameter(true)
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON)
            .mediaType("txt", MediaType.TEXT_PLAIN);
    }
}
```

Lúc đó `?format=json`/`?format=txt` có thể tác động đến requested media type và mapping tương ứng. **Không chép lớp cấu hình này vào dự án mà vẫn mong các test chỉ kiểm tra Accept có cùng ý nghĩa khi request chứa format parameter**: chiến lược tham số có thể tác động mức ưu tiên nếu được kích hoạt. Hãy tự định nghĩa rõ hợp đồng khi Accept và `format` mâu thuẫn.

Lưu ý:

1. Bật `favorParameter(true)` là quyết định API design, **không phải sửa lỗi “Spring không hiểu Accept”**.
2. Danh sách mapping media type như `json`, `txt` cần được kiểm soát; đừng để client đặt tên extension/media type tùy ý.
3. Khi dùng query parameter, phải xét **cache key** (URI query là một phần target), khác với cache theo Accept header.
4. Khuyến nghị chung là tránh phụ thuộc vào **path extension** như `/users.json` để chọn định dạng trong dự án Spring MVC mới. Suffix routing có lịch sử liên quan parsing/ambiguity và rủi ro reflected file download (RFD).
5. Nếu API chỉ cam kết JSON, cấu hình đơn giản `produces=application/json` thường rõ ràng hơn một loạt chiến lược fallback mơ hồ.

### 9.1. Có nên ép `defaultContentType`?

Spring MVC cho phép cấu hình default content type trong content negotiation. Nhưng chọn default phải theo hợp đồng ứng dụng: nếu API chỉ có JSON, JSON là lựa chọn hợp lý; nếu resource có nhiều format, hãy xác định rõ client không gửi Accept cần nhận bản nào, rồi **kiểm thử**. Không suy ra chỉ cần `defaultContentType` thì mọi handler `produces` ngang nhau tự động được phân giải chắc chắn.

Nếu server phải từ chối request thiếu `Accept` theo quy tắc riêng, đó là **chính sách ứng dụng tùy chỉnh**, không phải chuẩn HTTP mặc định. Thông thường không nên bắt client khai báo `Accept` khi chỉ phục vụ một định dạng.

## 10. Nội dung mặc định, 406 và trường hợp không có converter

### 10.1. Khi nào 406?

Theo HTTP, server có thể trả 406 khi không có representation hợp với `Accept`; RFC cũng cho phép bỏ qua preferences trong những trường hợp nhất định. **Spring MVC với ràng buộc `produces` rõ ràng thường trả 406** khi path/method phù hợp nhưng `Accept` không khớp, thông qua `HttpMediaTypeNotAcceptableException`.

Ví dụ `GET /api/media/json-only/7` có mapping GET, client gửi `Accept: application/xml`: lỗi là **406**, không phải 404/405/415.

Không nên suy luận từ status 406 rằng controller đã chạy; với `produces`, Spring có thể loại mapping trước khi gọi method. Nếu mapping được chọn nhưng converter không ghi được, cũng có thể có exception trong giai đoạn ghi response; tùy trường hợp và phiên bản, không phải mọi lỗi serialize đều biến thành 406 (có lỗi máy chủ 500).

### 10.2. Khi nào 415?

`415 Unsupported Media Type` phản ánh **request representation** không được hỗ trợ: `Content-Type` của body không phù hợp `consumes` hoặc decoder của server. Dù client gửi `Accept: application/json`, body vẫn có thể là `text/plain` và dẫn đến 415. `HttpMediaTypeNotSupportedException` là exception Spring thường gặp.

### 10.3. Khi nào 400, 404, 405?

- `400`: JSON sai cú pháp, body không deserialize được, hoặc binding/validation không hợp lệ; có thể xảy ra khi `Content-Type` vẫn đúng.
- `404`: URL không có mapping/resource phù hợp.
- `405`: URL phù hợp nhưng HTTP method không hỗ trợ; thường có header `Allow`.
- `406`: response media type không thể thỏa `Accept`.
- `415`: request body media type không được hỗ trợ.

Nếu request vi phạm **nhiều điều kiện cùng lúc**, đừng dự đoán lỗi bằng bảng trên theo thứ tự tuyệt đối; giai đoạn mapping, converters, filters, exception handlers và customizations có thể quyết định status xuất hiện trước.

### 10.4. `Content-Type` trên response lỗi không nhất thiết giống response thành công

Khi Spring Boot dùng controller advice hoặc `ProblemDetail`, response lỗi có thể là `application/problem+json`, HTML error page hoặc body rỗng tùy cấu hình. Không kết luận sai rằng endpoint đang trả XML chỉ vì test 406 không có body JSON; lỗi negotiation có thể yêu cầu fallback có chủ đích để client vẫn đọc được thông điệp. Response `406` không đảm bảo liệt kê đầy đủ tất cả representation được hỗ trợ; muốn client biết capabilities, có thể mô tả trong OpenAPI hoặc tài liệu API.

## 11. Media type có suffix +json và versioning

Một số API dùng vendor media type như:

```http
Accept: application/vnd.example.item.v1+json
```

Ý định là yêu cầu một representation có media type **cụ thể**. Các JSON converter hiện đại có thể hỗ trợ nhóm `application/*+json`, nhưng **mapping `produces = application/json` không mặc nhiên đồng nghĩa với mọi vendor media type**. Nếu muốn endpoint nhận `application/vnd.example.item.v1+json`, hãy khai báo `produces` tương ứng và kiểm tra converter hỗ trợ ghi cùng kiểu đó.

Ví dụ minh họa đường mở rộng:

```java
@GetMapping(
    path = "/versioned/{id}",
    produces = "application/vnd.example.item.v1+json")
public Item versioned(@PathVariable("id") long id) {
    return new Item(id, "Pen");
}
```

Đoạn này **phải được thêm như một method trong controller nơi kiểu `Item` đã tồn tại** (hoặc tự định nghĩa Item/import annotation); không phải một tệp Java đứng riêng. Không tự động xem `Accept: application/json` là tương đương vendor media type trên. Versioning qua media type có lợi khi cần định nghĩa representation rõ ràng, nhưng làm phức tạp client, caching và docs; cân nhắc với URL/version header tùy mục tiêu.

Khi dùng `application/problem+json`, hãy phân biệt nó với media type thành công của resource. Response lỗi là một contract khác, không tự chứng minh endpoint hỗ trợ problem+json như một representation thành công.

## 12. Cache: khi response phụ thuộc Accept, cân nhắc Vary

Giả sử cùng `GET /api/media/items/7` trả JSON hoặc text theo `Accept`. Cache trung gian không nhận biết biến thể có thể phục vụ bản text cho client chỉ muốn JSON nếu chỉ khóa cache bằng URL. Header:

```http
Vary: Accept
```

thông báo cho cache rằng việc lựa chọn response phụ thuộc header `Accept` của request. Cần xem xét phát header này **cho các response liên quan**, không chỉ một nhánh thành công. Spring hay reverse proxy **có thể** thêm `Vary` ở một số tính năng như CORS, nhưng bạn không nên mặc định mọi response content negotiation đều tự có `Vary: Accept` trong mọi cấu hình.

Có thể gắn thêm header từ ứng dụng cho response có nhiều variant:

```java
@GetMapping(path = "/cached/{id}", produces = "application/json")
public ResponseEntity<Item> cachedJson(@PathVariable long id) {
    return ResponseEntity.ok()
            .varyBy("Accept")
            .body(new Item(id, "Pen"));
}
```

Đây là method minh họa đặt trong controller có imports `ResponseEntity`, `GetMapping`, `PathVariable` và record `Item` phù hợp; **không phải nguyên chương trình độc lập**. Nếu dự án bạn dùng phiên bản API không hỗ trợ builder method ở trên, có thể dùng `header(HttpHeaders.VARY, HttpHeaders.ACCEPT)` trong builder. `Vary` phải phản ánh đúng các header thực sự ảnh hưởng representation, không phải thay thế policy cache, TTL hay ETag.

Lưu ý: nếu response chứa dữ liệu theo user/authorization, riêng `Vary: Accept` **không làm nội dung cá nhân an toàn để shared-cache**. Vẫn cần `Cache-Control`, xác thực và phân quyền phù hợp.

## 13. Chẩn đoán production: từ request tới converter

Khi client nhận định dạng bất ngờ hoặc 406:

1. **Capture request thật:** path, method, `Accept`, `Content-Type`, body; công cụ như browser, curl, API gateway có thể tự thêm `Accept: */*` hoặc nhiều loại.
2. **Tách chiều đọc/ghi:** 415 nghi `Content-Type`/`consumes`, 406 nghi `Accept`/`produces`/canWrite; 400 nghi cú pháp/deserialization.
3. **Kiểm tra mapping:** phương thức controller và `@RequestMapping(produces=...)` ở class/method; method-level ghi đè class-level. Kiểm tra path/method trước khi đi sâu vào format.
4. **Liệt kê representation thật sự có:** không chỉ annotation mà còn thư viện Jackson XML, converter, serialization của Java return type.
5. **Rà q/wildcard:** xem q=0, q thiếu (mặc định 1), wildcard và subtype; đừng đơn giản “lấy phần tử Accept đầu tiên”.
6. **Kiểm tra chiến lược negotiation:** mặc định Spring MVC 6.x dùng Accept; tìm custom `WebMvcConfigurer`, `ContentNegotiationManager`, `favorParameter`, `defaultContentType`.
7. **Kiểm tra cách trả `String`:** `@Controller` không có `@ResponseBody` có thể trả view name; `@RestController` trả response body.
8. **Kiểm tra converter:** nếu DTO trả JSON lỗi khi gặp kiểu đặc biệt (cycles, lazy proxies, unsupported serializers), không thể chỉ sửa `Accept` rồi chắc chắn giải quyết được.
9. **Xem cache/gateway:** cùng URL có nhiều format cần `Vary: Accept` và cấu hình cache thích hợp; proxy có thể xóa/chỉnh header.
10. **Đừng khẳng định body lỗi mặc định cố định:** Spring Boot/ProblemDetail/advice có thể khác nhau. Kiểm tra status và headers, sau đó log an toàn.
11. **Quan sát mapping đã đăng ký:** Spring Boot Actuator `/actuator/mappings` nếu dependency và cấu hình cho phép; không mở actuator nhạy cảm công khai chỉ để debug.
12. **Kiểm thử từng biến:** giữ URL/method cố định rồi lần lượt thay `Accept`; thử wildcard, q và không Accept. Sau đó riêng rẽ thay `Content-Type` ở POST.

Đối với logging, cân nhắc mức debug cho những lớp chọn mapping/HTTP converter trong môi trường kiểm thử; tránh log body, token và dữ liệu cá nhân chỉ để điều tra negotiation.

## 14. Thiết kế API: lựa chọn thực tế

**API JSON thuần:** khai báo `produces=application/json` ở endpoint, có Jackson, và dùng DTO/record làm response. `Accept: application/json` đáp ứng, `Accept: application/xml` thường 406. Đây là thiết kế đơn giản, dễ tài liệu hóa.

**API nhiều định dạng:** định nghĩa danh sách representation được hỗ trợ; cung cấp converter cho mỗi định dạng; quyết định response mặc định rõ ràng; mô tả `Accept` và q; kiểm tra status/content-type và `Vary`. Nếu dùng nhiều handler cùng URL phân biệt `produces`, test cả request client gửi header cụ thể lẫn trường hợp thiếu/tie để tránh lựa chọn mơ hồ.

**API export/báo cáo:** nếu JSON, CSV, PDF là các **định dạng xuất có cấu trúc khác nhau** và có logic tạo tài liệu khác nhau, có thể dùng `Accept` hoặc một URL export riêng (`/reports/42.csv` chỉ khi được thiết kế/route tường minh). Không chỉ đổi header `Content-Type` rồi gửi body vẫn là JSON; media type phải phản ánh nội dung.

**Client gọi API:** đặt `Accept` theo định dạng mình thực sự đọc được, không luôn để `*/*`. Đặt `Content-Type` theo body **mình thực sự gửi**. Nếu API có nhiều representation, client dùng Accept trọng số khi sẵn sàng nhận nhiều kiểu.

## 15. Lỗi phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Hiểu `Accept` là định dạng request body | Debug nhầm 406 thành 415 | Phân biệt `Accept` và `Content-Type` |
| Chỉ khai báo `produces="application/xml"` mà không cài converter | Không thể serialize object thành XML đúng | Thêm/cấu hình converter và test với DTO thực |
| Trả `String` với `@Controller` rồi mong response body | Spring có thể coi String là view name | Dùng `@ResponseBody`/`@RestController` |
| Mong `GET /items.json` tự đổi format theo đuôi | Routing 6.x mặc định không cần suffix strategy | Dùng Accept hoặc khai báo route explicit |
| Mong `?format=xml` hoạt động mặc định | Parameter strategy chưa bật | Cấu hình rõ hoặc dùng Accept |
| Bỏ qua q hoặc wildcard | Chọn nhầm media type | Dùng parser/negotiation của framework |
| Cho rằng q=0.1 nghĩa là bị cấm | Từ chối representation vẫn hợp lệ | Chỉ q=0 loại trừ; q dương là chấp nhận |
| Thiếu test cho Accept không tương thích | Chỉ phát hiện 406 trên production | Test bằng MockMvc và client thực |
| Bỏ qua `Vary: Accept` khi caching nhiều variant | Cache có thể trộn JSON và text | Thiết kế Vary và cache policy rõ |
| Dùng JSON converter nhưng đổi `Content-Type` thành XML | Payload và nhãn không khớp | Serialize XML thật hoặc không công bố XML |
| Quên exception/response lỗi cũng có media type | Client không đọc được lỗi nhất quán | Thiết kế lỗi riêng và test trường hợp 406 |
| Dùng wildcard `*/*` trong test rồi hardcode JSON | Có thể chọn representation khác khi server đổi | Test với Accept cụ thể khi cần hợp đồng ổn định |

## 16. Câu hỏi tự kiểm tra

**1.** Một GET chỉ `produces = application/json`, client gửi `Accept: application/xml`. Status thường là gì?

**Đáp án:** `406 Not Acceptable`; đường dẫn/method có thể đúng nhưng không có representation phù hợp.

**2.** Client gửi JSON body kèm `Content-Type: text/plain` tới POST chỉ `consumes = application/json`, nhưng đặt `Accept: application/json`. Có giải quyết lỗi không?

**Đáp án:** Không. `Accept` không sửa nhãn của request body; thường nhận `415`.

**3.** `Accept: text/plain;q=0.8, application/json;q=0.2` có buộc server luôn chọn text không?

**Đáp án:** Không. Nó ưu tiên text **nếu server có bản text**; JSON với q=0.2 vẫn chấp nhận nếu chỉ có JSON.

**4.** `Accept: */*` có đồng nghĩa “chỉ JSON” không?

**Đáp án:** Không. Nó chấp nhận mọi media type.

**5.** Nếu JSON converter đã có, `produces = "application/xml"` có đủ để xuất XML không?

**Đáp án:** Không. Cần XML converter/serializer thực sự hỗ trợ return type, đồng thời mapping tương thích.

**6.** Hai handler cùng GET và URL nhưng `produces` khác nhau có thể đăng ký không?

**Đáp án:** Có. Đây là một cách tạo representation riêng theo Accept; phải xác định cách xử lý khi client không có Accept hoặc sở thích ngang nhau.

**7.** Cùng URL trả JSON hoặc text tùy `Accept`; cache trung gian cần chú ý header nào?

**Đáp án:** `Vary: Accept`, cùng policy cache phù hợp.

**8.** Vì sao 406 không luôn đồng nghĩa method controller đã chạy?

**Đáp án:** `produces` có thể bị loại ngay tại giai đoạn chọn handler trước khi gọi controller.

## 17. Tài liệu tham khảo

- Spring Framework 6.2 — Content Types và cấu hình negotiation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/content-negotiation.html
- Spring Framework 6.2 — Mapping Requests, điều kiện produces/consumes: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework 6.2 — HTTP Message Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html
- Spring Framework 6.2 — @ResponseBody: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework 6.2 — Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- RFC 9110 — HTTP Semantics, Accept/q/wildcard/Vary và 406/415: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
