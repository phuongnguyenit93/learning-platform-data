# Cấu hình content negotiation và tránh suy luận định dạng không mong muốn trong Spring MVC

## 1. Content negotiation là gì?

**Content negotiation** là cơ chế chọn biểu diễn (representation) của tài nguyên HTTP phù hợp với yêu cầu client và khả năng của server. Cùng một dữ liệu nghiệp vụ có thể được biểu diễn thành JSON, XML, HTML hoặc văn bản thuần; nhưng ứng dụng không nhất thiết phải hỗ trợ mọi định dạng.

Ví dụ:

```http
GET /api/books/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Client nói rằng nó muốn nhận JSON. Nếu endpoint có thể trả JSON, response điển hình:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Java"}
```

**Mục tiêu của cấu hình an toàn:** Định dạng response phải được quyết định một cách rõ ràng, có thể kiểm thử và không bị một phần mở rộng tên file, query parameter hoặc header không tin cậy làm ứng dụng bất ngờ chuyển sang kiểu dữ liệu mà sản phẩm không định hỗ trợ.

Trong Spring MVC, cần phân biệt ít nhất ba vấn đề:

- **Định dạng client chấp nhận:** thường đọc từ header `Accept`.
- **Định dạng request body gửi tới server:** đọc từ header `Content-Type`.
- **Định dạng server thực sự có thể tạo:** phụ thuộc `@RequestMapping(produces=...)`, `HttpMessageConverter`, `ViewResolver` và cấu hình ứng dụng.

Content negotiation không tự biến mọi đối tượng Java thành mọi MIME type, cũng không có nghĩa rằng server phải trả định dạng được yêu cầu nếu nó không có khả năng tạo định dạng đó.

## 2. Accept, Content-Type, produces và consumes

| Khái niệm | Chiều dữ liệu | Ý nghĩa |
|---|---|---|
| `Accept: application/json` | Client → server, metadata của request | Client muốn nhận response có media type JSON |
| `Content-Type: application/json` trong request | Client → server | Request body đang gửi là JSON |
| `produces = "application/json"` | Khai báo handler | Handler chỉ được chọn cho media type response được khai báo là phù hợp |
| `consumes = "application/json"` | Khai báo handler | Handler yêu cầu request có media type đầu vào phù hợp |
| `Content-Type` trong response | Server → client | Định dạng response thực tế |
| `HttpMessageConverter` | Spring MVC runtime | Chuyển đổi object ↔ HTTP request/response body theo khả năng hỗ trợ |

Ví dụ controller:

```java
@PostMapping(
    path = "/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public Book create(@RequestBody Book book) {
    return book;
}
```

- `consumes` đối chiếu **request Content-Type**.
- `produces` đối chiếu **Accept / media types mà client yêu cầu**.
- `@RequestBody` nhờ `HttpMessageConverter` đọc dữ liệu đầu vào.
- `@ResponseBody` (hoặc `@RestController`) nhờ converter tạo response body.

Nếu client muốn XML mà chỉ có handler `produces=application/json`, Spring MVC có thể trả **406 Not Acceptable**. Nếu client gửi `Content-Type: text/plain` cho handler chỉ `consumes=application/json`, lỗi điển hình là **415 Unsupported Media Type**.

Không đảo lộn hai status này: 406 liên quan **representation đầu ra**, 415 liên quan **media type đầu vào**.

## 3. Cơ chế chọn representation trong Spring MVC

Luồng khái quát:

```text
HTTP Request
   |
   |-- URL + HTTP method + Content-Type + Accept
   v
DispatcherServlet
   |
   v
HandlerMapping
   |-- đối chiếu mapping, consumes, produces
   v
HandlerAdapter -> Controller method
   |
   |-- @ResponseBody hoặc ResponseEntity?
   |       |
   |       v
   |   HttpMessageConverter
   |   (chọn media type tương thích, serialize body)
   |
   |-- Trả tên view / ModelAndView?
           |
           v
       ViewResolver / View
       (chọn và render representation tương ứng)
   |
   v
HTTP Response
```

Một phần quan trọng trong việc xác định media type client muốn nhận là `ContentNegotiationManager`. Nó tập hợp các `ContentNegotiationStrategy` (ví dụ header strategy hoặc parameter strategy). Đối với Spring MVC hiện đại, mặc định cơ bản là dựa trên **Accept header**; không tự suy đoán định dạng từ hậu tố URL.

Có hai luồng trả response quan trọng:

1. **REST/response body:** `@RestController`, `@ResponseBody` hoặc `ResponseEntity` được xử lý bởi các `HttpMessageConverter` như Jackson converter cho JSON. Chỉ khi converter có khả năng viết dữ liệu theo media type thích hợp thì response mới được tạo đúng định dạng.
2. **Server-side rendered view:** `@Controller` trả tên view như `"reports/summary"` có thể đi qua `ViewResolver` và `View`. `ContentNegotiatingViewResolver` (nếu được cấu hình) còn có thể tham gia chọn view theo media type. Đây không phải luồng mặc định của một endpoint JSON `@RestController`.

Content negotiation ảnh hưởng tới việc chọn handler và converter/view, nhưng **không phải cơ chế xác thực, phân quyền, input validation hay định tuyến chính của ứng dụng**.

## 4. Mặc định của Spring MVC: ưu tiên Accept, tránh hậu tố URL

Trong Spring Framework 6.x và tài liệu Spring Boot 3.5, chiến lược nội dung mặc định dựa trên `Accept` header; cơ chế suy luận định dạng từ phần mở rộng file trong URL không được khuyến nghị.

Ví dụ một request:

```http
GET /api/books/42.json HTTP/1.1
Accept: application/json
```

Không nên mặc định hiểu `.json` ở cuối path có nghĩa rằng Spring MVC phải gọi mapping `/api/books/42` rồi tự đổi representation sang JSON. Path `/api/books/42.json` là một đường dẫn khác. Nó có thể không khớp mapping, hoặc có thể khớp biến đường dẫn `{id}` rồi gây lỗi chuyển đổi kiểu nếu controller khai báo `long id` — không có status cố định cho mọi cấu trúc mapping.

**Lý do nên tránh suy luận qua phần mở rộng URL:**

- URL có dấu chấm trong mã định danh, tên miền hoặc phiên bản không nhất thiết là yêu cầu đổi media type.
- Suffix pattern matching có thể làm một route vô tình nhận thêm nhiều URL ngoài ý muốn.
- Dựa vào phần mở rộng có thể khiến API và tầng security hiểu các URL không đồng nhất.
- Các dạng phản chiếu dữ liệu và tải file có thể tăng rủi ro **Reflected File Download (RFD)** nếu ứng dụng chấp nhận extension tùy ý và trả nội dung không kiểm soát.
- Cache/proxy có thể lưu response không đúng representation khi không phân biệt các header request ảnh hưởng đến kết quả.

Theo tài liệu Spring Framework, `ContentNegotiationConfigurer.favorPathExtension(...)` đã bị deprecated từ Spring Framework 5.2.4; cơ chế này mặc định tắt từ 5.3. Trong ứng dụng mới, **không bật lại** để sửa những client không gửi `Accept` đúng. Nếu thật sự cần lựa chọn theo URL, query parameter có allowlist là giải pháp ít nhập nhằng hơn.

Tương tự, Spring Boot không bật suffix pattern matching mặc định. Không cấu hình wildcard `/resource.*` để giả lập negotiation nếu không có yêu cầu thật sự và kiểm thử chặt chẽ.

## 5. Cấu hình an toàn nhất: Accept header + produces rõ ràng

Với API chỉ hỗ trợ JSON:

```java
@GetMapping(
    path = "/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
public Book findById(@PathVariable long id) {
    return new Book(id, "Java");
}
```

Các hành vi mong đợi khi Jackson JSON converter có mặt:

| Request Accept | Kết quả phù hợp |
|---|---|
| `application/json` | Endpoint có thể trả JSON |
| `application/*` | Có thể nhận JSON vì tương thích |
| `*/*` | Có thể nhận JSON vì client chấp nhận mọi type |
| Không gửi `Accept` | Endpoint có thể trả JSON; không cần tự đoán từ `.json` |
| `application/xml` | Không tương thích với `produces=application/json`; thường trả 406 |
| `text/html` | Không tương thích với `produces=application/json`; thường trả 406 |

`produces` giúp định nghĩa **hợp đồng đầu ra**, nhưng việc serialize còn phụ thuộc converter. Không thêm converter XML một cách ngẫu nhiên vào classpath rồi coi nó là đầu ra bắt buộc; nếu muốn hỗ trợ XML, hãy tuyên bố và kiểm thử rõ media type đó.

Đối với response body cần cố định rõ `Content-Type`, có thể tạo `ResponseEntity` với media type cụ thể; vẫn phải đảm bảo converter hỗ trợ và mapping phù hợp. Với API JSON, `produces` thường là mức ràng buộc đầu tiên dễ hiểu nhất.

**Tránh vô tình chỉ định `produces={"application/json","text/html"}` khi endpoint thực tế chỉ tạo JSON.** Việc công bố quá nhiều định dạng gây hiểu nhầm về hợp đồng và có thể khiến hành vi chọn representation không nhất quán.

## 6. Ví dụ ứng dụng Spring Boot 3.5 + Java 17

Ví dụ dùng Spring MVC, một API chỉ chấp nhận và tạo JSON. Tạo một project Spring Boot 3.5, Java 17 với dependency `spring-boot-starter-web` (thông thường đã mang theo Jackson JSON converter).

Trong `pom.xml` có dependency sau, giả định project đã có Spring Boot parent hoặc dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Thư mục mã nguồn:

```text
src/main/java/com/example/negotiation/
  NegotiationApplication.java
  BookController.java
src/main/resources/
  application.properties
```

### 6.1. Lớp khởi động

File `src/main/java/com/example/negotiation/NegotiationApplication.java`:

```java
package com.example.negotiation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NegotiationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NegotiationApplication.class, args);
    }
}
```

### 6.2. Controller với produces và consumes

File `src/main/java/com/example/negotiation/BookController.java`:

```java
package com.example.negotiation;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Book find(@PathVariable long id) {
        return new Book(id, "Java");
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public Book create(@RequestBody Book book) {
        return book;
    }

    public record Book(long id, String title) {
    }
}
```

`record Book` của Java 17 được Jackson hỗ trợ trong project phù hợp. `@RestController` khiến giá trị `Book` được ghi thành response body qua JSON converter, không thông qua `ViewResolver`.

Đây là ví dụ học tập: `create` trả lại dữ liệu đã nhận để làm rõ conversion; ứng dụng thật cần validation, service, persistence, xử lý lỗi và kiểm tra quyền. Không coi đây là API lưu trữ dữ liệu hoàn chỉnh.

### 6.3. Cấu hình application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.mvc.contentnegotiation.favor-parameter=false
```

Không cần cấu hình này khi mặc định đã tắt parameter negotiation; viết ra nhằm khẳng định chính sách: response được chọn chủ yếu bằng `Accept`, còn `?format=xml` không tự đổi response type.

Trong project Maven có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Các lệnh `curl` dùng để quan sát sự khác nhau:

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/api/books/42
```

Response body mong đợi:

```json
{"id":42,"title":"Java"}
```

Status bình thường là `200`, response `Content-Type` tương thích `application/json`.

Client yêu cầu XML:

```bash
curl -i -H 'Accept: application/xml' http://localhost:8080/api/books/42
```

Vì handler chỉ `produces=application/json`, kết quả thông thường là **406 Not Acceptable**. Nội dung lỗi có thể phụ thuộc cấu hình Spring Boot, `ProblemDetail`, error handling và content negotiation cho response lỗi; không coi body lỗi là chuỗi cố định.

Client POST sai `Content-Type`:

```bash
curl -i -X POST -H 'Content-Type: text/plain' -H 'Accept: application/json' --data 'hello' http://localhost:8080/api/books
```

Mapping chỉ `consumes=application/json` nên kết quả thông thường là **415 Unsupported Media Type**.

POST JSON đúng định dạng:

```bash
curl -i -X POST -H 'Content-Type: application/json' -H 'Accept: application/json' --data '{"id":7,"title":"Spring"}' http://localhost:8080/api/books
```

Nếu body hợp lệ, response thường có status **201 Created**, và JSON body:

```json
{"id":7,"title":"Spring"}
```

Lưu ý: `-i` cho curl in cả status và response headers. Các body được ghi ở trên là phần minh họa mong đợi, không phải bản ghi toàn bộ response.

## 7. Khi nào dùng query parameter format?

Một số client, ví dụ trình duyệt, API gateway cũ hoặc công cụ export, khó điều khiển `Accept` header. Khi đó có thể cho phép định dạng qua query parameter, ví dụ:

```text
GET /api/export?format=json
GET /api/export?format=txt
```

Đây phải là **lựa chọn thiết kế có chủ đích**. Không bật negotiation từ mọi query parameter hay từ extension ngẫu nhiên.

Spring Boot 3.5 hỗ trợ cấu hình:

```properties
spring.mvc.contentnegotiation.favor-parameter=true
spring.mvc.contentnegotiation.parameter-name=format
spring.mvc.contentnegotiation.media-types.json=application/json
spring.mvc.contentnegotiation.media-types.txt=text/plain
```

Tương đương:

```yaml
spring:
  mvc:
    contentnegotiation:
      favor-parameter: true
      parameter-name: format
      media-types:
        json: application/json
        txt: text/plain
```

Khi bật `favor-parameter=true`, Spring MVC có thể ưu tiên định dạng được yêu cầu bằng `?format=...` trước `Accept` theo thứ tự strategy đã cấu hình. Vì điều này áp dụng trên phạm vi MVC context, hãy kiểm tra những endpoint khác đang dựa vào `Accept` để tránh thay đổi behavior ngoài dự kiến.

Việc đăng ký `json` hay `txt` chỉ cho Spring biết cách chuyển **giá trị parameter → media type**; không tự động thêm converter hoặc một handler có thể xuất `text/plain`. Nếu handler chỉ `produces=application/json`, request `?format=txt` vẫn có thể không có representation phù hợp và trả 406.

**Khuyến nghị thiết kế:** Nếu chỉ một endpoint export cần nhiều định dạng, có thể tạo route tường minh như `/export.json` và `/export.txt`, hoặc tự đọc parameter `format` tại riêng controller rồi kiểm tra danh sách giá trị cho phép, thay vì đổi chính sách negotiation của toàn bộ ứng dụng. Với URL chứa extension, các route phải được khai báo **tường minh**, không dựa vào suffix matching tự động.

## 8. Cấu hình programmatic bằng WebMvcConfigurer

Nếu cần cấu hình bằng Java, Spring MVC cung cấp `WebMvcConfigurer.configureContentNegotiation`.

Ví dụ cho Spring Boot 3.x và Spring Framework 6.x, file `MvcNegotiationConfig.java`:

```java
package com.example.negotiation;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.config.annotation.ContentNegotiationConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcNegotiationConfig implements WebMvcConfigurer {

    @Override
    public void configureContentNegotiation(
            ContentNegotiationConfigurer configurer) {
        configurer
            .favorParameter(true)
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON)
            .mediaType("txt", MediaType.TEXT_PLAIN)
            .useRegisteredExtensionsOnly(true)
            .ignoreAcceptHeader(false);
    }
}
```

Giải thích:

- `favorParameter(true)`: bật chiến lược đọc query parameter.
- `parameterName("format")`: dùng đúng tham số `format`.
- `mediaType("json", ...)`, `mediaType("txt", ...)`: mapping từ giá trị khóa sang media type được đăng ký.
- `useRegisteredExtensionsOnly(true)`: yêu cầu chiến lược parameter chỉ sử dụng các mapping đã được đăng ký, tránh tự tra suy đoán media type không nằm trong danh sách.
- `ignoreAcceptHeader(false)`: vẫn xem xét `Accept` khi cần theo cấu hình strategy.

Ví dụ này **là phương án thay thế** cho việc khai báo cùng các setting qua `application.properties`, không phải yêu cầu phải cấu hình cả hai nơi. Tránh để nhiều nguồn cấu hình định nghĩa trái ngược chính sách negotiation.

**Không thêm `@EnableWebMvc` chỉ để sửa content negotiation** trong ứng dụng Spring Boot. `WebMvcConfigurer` thường có thể mở rộng cấu hình MVC được auto-configure; `@EnableWebMvc` thay đổi chế độ tự cấu hình và có thể khiến bạn phải cấu hình thủ công nhiều thành phần khác.

Nếu cần API hoàn toàn header-based, bỏ bean config phía trên và giữ `spring.mvc.contentnegotiation.favor-parameter=false` hoặc không cấu hình gì thêm.

## 9. Vì sao không nên bật suy luận theo file extension?

Các API cũ từng dựa vào URL như:

```text
/api/books/42.json
/api/books/42.xml
/api/books/42.pdf
```

Rồi tự ánh xạ phần mở rộng tới media type mà không có route tường minh. Cách làm này thường khó bảo trì vì:

1. **Routing mơ hồ:** dấu chấm có thể là một phần của id, tên file hoặc dữ liệu định danh.
2. **Security mismatch:** tầng proxy/security và controller có thể không đánh giá URL mở rộng theo cùng quy tắc.
3. **RFD:** reflected file download có thể xảy ra trong một số cấu hình khi nội dung phản chiếu được tải về dưới tên file nguy hiểm.
4. **Format surprise:** thêm một converter vào classpath có thể vô tình mở rộng định dạng response có thể được tạo.
5. **Cache confusion:** cùng URL và các biểu diễn khác nhau phải có chính sách cache rõ ràng.

Spring MVC có biện pháp phòng vệ RFD ở một số trường hợp: thêm header dạng `Content-Disposition: inline;filename=f.txt` khi path có extension không an toàn/chưa được đăng ký. Đây là cơ chế giảm rủi ro của Framework, **không thay thế** cho việc thiết kế URL và media type an toàn.

Với API mới, nên chọn một trong hai:

- Dùng `Accept` + `produces` tường minh khi một URL có thể có nhiều representation.
- Dùng **URL/route rõ ràng** cho các thao tác export/download: `/reports/{id}/download`, `/reports/{id}/csv` hoặc route khác được đăng ký chính thức; trả `Content-Disposition` và media type phù hợp.

Không sử dụng `favorPathExtension(true)` để giải quyết lỗi 406 mà chưa biết nguyên nhân.

## 10. Accept có quality factor, wildcard và default

`Accept` có thể chứa nhiều media type và độ ưu tiên:

```http
Accept: application/json;q=0.9, text/plain;q=0.5
```

Client tuyên bố JSON được ưu tiên hơn văn bản thuần. Ví dụ khác:

```http
Accept: application/*;q=0.8, */*;q=0.1
```

Những điều cần nhớ:

- `q` là **trọng số ưu tiên** từ 0 đến 1 theo HTTP semantics; media type với `q=0` được coi là không chấp nhận.
- Wildcard như `*/*` biểu thị client chấp nhận nhiều định dạng, **không bắt buộc server trả một định dạng cụ thể**.
- Nếu `Accept` không được gửi, client nhìn chung không giới hạn representation ở tầng header.
- Khi thiếu `Accept`, không nên suy đoán `application/json` chỉ vì URL có `.json`; hãy dùng hợp đồng endpoint và khả năng converter/view.
- Thứ tự chọn representation còn phụ thuộc `produces`, khả năng serialize và thuật toán chọn media type của Spring MVC. Không nên tự khẳng định rằng danh sách `Accept` luôn quyết định kết quả, đặc biệt khi server có nhiều response formats.

Nếu API **chỉ hỗ trợ JSON**, khai báo `produces=application/json` là một lựa chọn rõ hơn so với việc cố thay đổi `defaultContentType` toàn cục.

Spring Boot 3.5 có thêm property `spring.mvc.contentnegotiation.default-content-types` để cấu hình default content types khi không có yêu cầu cụ thể. Chỉ sử dụng khi bạn thực sự muốn chính sách fallback toàn cục, đã đọc đúng tài liệu phiên bản và kiểm tra ảnh hưởng tới HTML views, problem responses và các endpoint khác.

## 11. Phân biệt content negotiation với định dạng dữ liệu nội bộ

Content negotiation là hợp đồng ở **lớp HTTP representation**. Nó không đồng nghĩa:

- Đổi loại đối tượng Java/domain model.
- Tự tạo bộ chuyển đổi XML, PDF hoặc CSV khi dự án chưa có serializer tương ứng.
- Dịch nội dung theo ngôn ngữ người dùng; việc đó liên quan `Accept-Language` và locale.
- Thay đổi request routing hoặc authentication.
- Chấp nhận tất cả MIME type của client mà không kiểm tra.
- Dự đoán file format từ đuôi của một tên file trong JSON body.

Tương tự, việc thêm dependency Jackson XML có thể khiến Spring có thêm converter hỗ trợ XML, nhưng **không có nghĩa mọi endpoint đều nên phát XML**. `produces` giúp giới hạn media type nào được công bố. Đừng phụ thuộc vào sự có mặt ngẫu nhiên của converter để xác định contract API.

Với response ở dạng HTML view, đừng chỉ chuyển `Content-Type` thành `application/json` rồi mong template render được JSON đúng chuẩn. Nếu cần JSON, hãy thiết kế handler dùng `@ResponseBody` hoặc `ResponseEntity` và một converter phù hợp.

## 12. 406, 415, 400 và 404: phân biệt khi debug

| Status | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| **406 Not Acceptable** | Không có representation phù hợp với `Accept` / `produces` | Client yêu cầu XML, endpoint chỉ trả JSON |
| **415 Unsupported Media Type** | Media type request body không phù hợp `consumes` hoặc converter đọc | POST `text/plain` tới endpoint chỉ nhận JSON |
| **400 Bad Request** | Cú pháp, dữ liệu hoặc kiểu tham số không hợp lệ | URL `/books/42.json` khớp `{id}` kiểu `long`, nhưng không chuyển được |
| **404 Not Found** | Không có mapping/resource phù hợp | Request tới path không được ánh xạ |

Trạng thái cụ thể có thể phụ thuộc các điều kiện mapping khác, exception handler hoặc proxy, nên cần xem exception thực tế. Không coi tất cả lỗi 406 là do thiếu Jackson hay tất cả lỗi 415 là do `Accept`.

Nếu muốn cho client biết rõ những media type hợp lệ, ghi tài liệu OpenAPI và test tự động; không dựa vào client thử từng định dạng rồi suy luận.

## 13. Kiểm thử content negotiation bằng MockMvc

Với Spring Boot 3.5 và `spring-boot-starter-test`, có thể kiểm thử các cam kết của `BookController`.

File `src/test/java/com/example/negotiation/BookControllerTest.java`:

```java
package com.example.negotiation;

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
class BookControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void jsonRequestReturnsJson() throws Exception {
        mvc.perform(get("/api/books/42").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Java"));
    }

    @Test
    void xmlAcceptIsNotAvailable() throws Exception {
        mvc.perform(get("/api/books/42").accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void plainTextBodyIsNotAllowed() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void validJsonBodyIsCreated() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"id\":7,\"title\":\"Spring\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Spring"));
    }
}
```

Lưu ý lớp test này cần đúng package và dependency `spring-boot-starter-test` phù hợp với project Spring Boot 3.5. Với Spring Boot 4.x, tên package và starter test MVC có thể thay đổi; dùng tài liệu/test dependency tương ứng của bản đó.

Chạy trong project Maven:

```bash
./mvnw test
```

Các test tách biệt:

- Client `Accept: application/json` nhận JSON.
- Client chỉ chấp nhận XML nhận 406 khi endpoint chỉ hỗ trợ JSON.
- POST sai `Content-Type` nhận 415.
- POST JSON hợp lệ nhận 201.

Nếu ứng dụng bật `favor-parameter=true` như ở mục 7 hoặc 8, cần viết test thêm cho `?format=json`, `?format=txt`, định dạng không được đăng ký và trường hợp xung đột với `Accept`. Đó là chính sách **khác** với ví dụ test mặc định, nên đừng áp dụng các đoạn cấu hình trái ngược trong cùng một test mà không chỉnh kỳ vọng.

## 14. Cache, proxy và header Vary

Nếu cùng URL có thể trả nhiều representation dựa trên `Accept`, cache ở CDN hoặc reverse proxy cần phân biệt cache key theo header tương ứng. HTTP cung cấp `Vary` để khai báo các request header làm thay đổi representation:

```http
Vary: Accept
```

Khi có response khác nhau cho cùng URL phụ thuộc vào `Accept`, đây là tín hiệu quan trọng với shared cache. Nếu response còn phụ thuộc `Accept-Language` hoặc một header khác, chính sách `Vary` và cache key phải xét đúng các header đó.

Tuy nhiên, đừng cho rằng mọi endpoint Spring MVC luôn tự thêm `Vary: Accept` đúng ý bạn trong mọi trường hợp. Hãy kiểm tra response thực tế và cấu hình CDN/proxy. Response chứa dữ liệu cá nhân cần thêm chính sách `Cache-Control` phù hợp; `Vary` không thay thế chính sách bảo vệ dữ liệu.

Với `?format=json` và `?format=txt`, cache thường phân biệt URL theo query string, nhưng tùy cấu hình proxy có thể bỏ qua tham số. Hãy xác nhận cache key thay vì giả định.

## 15. An toàn định dạng response và header Content-Type

Tránh các hành vi "format surprise" còn bao gồm:

1. **Không phản chiếu tùy ý `Accept` hoặc `format` thành `Content-Type`** mà thiếu mapping đã đăng ký.
2. **Không dùng wildcard quá rộng** trong `produces` nếu hợp đồng API chỉ hỗ trợ một loại dữ liệu.
3. **Không render dữ liệu không tin cậy thành HTML mà thiếu escaping**, kể cả khi client gửi `Accept: text/html`.
4. **Không mở XML serialization không cần thiết** chỉ vì thêm converter, nhất là khi dữ liệu/serializer có cấu hình nguy hiểm.
5. **Không bật suffix inference** để giải quyết các vấn đề client legacy mà chưa đánh giá security.
6. **Đặt `Content-Type` chuẩn** cho response; với frontend browser, có thể sử dụng `X-Content-Type-Options: nosniff` như một lớp phòng vệ bổ sung (thường được Spring Security cung cấp khi cấu hình mặc định phù hợp).
7. **Với tải file**, sử dụng `Content-Disposition` và tên file an toàn, kiểm soát loại file được tạo; không suy luận download tùy ý theo extension người dùng gửi.

Các thuộc tính như CSRF, CORS và authentication là lớp bảo vệ riêng, không thể thay thế chỉ bằng content negotiation.

## 16. Quy trình triển khai và debug thực tế

Khi API trả `Content-Type` bất ngờ, hãy kiểm tra theo trình tự:

1. **Xác định endpoint.** Đọc `@GetMapping`, `@PostMapping`, `@RequestMapping`, đặc biệt `produces` và `consumes`.
2. **Ghi lại request.** Kiểm tra thực tế `Accept`, `Content-Type`, query `format` và path; chú ý proxy có thể sửa các header.
3. **Xem chính sách MVC.** `spring.mvc.contentnegotiation.favor-parameter`, `parameter-name`, `media-types.*`, `WebMvcConfigurer.configureContentNegotiation`.
4. **Xác định converter/view.** Ứng dụng có Jackson JSON/XML converter, String converter, Thymeleaf hay ContentNegotiatingViewResolver?
5. **Đối chiếu mapping và type.** Nếu chỉ hỗ trợ JSON, không vô tình tuyên bố HTML/XML ở `produces`.
6. **Đọc status và exception.** 406 khác 415; 404/400 có thể do path và binding.
7. **Kiểm tra đường dẫn có extension.** Xác nhận route thực sự được khai báo, không dựa vào suy luận cũ.
8. **Test matrix.** Thử `Accept: application/json`, `Accept: application/xml`, `Accept: */*`, không gửi `Accept`, query parameter cho phép/không cho phép và request có dấu chấm trong path.
9. **Kiểm tra cache/proxy.** `Vary`, cache key, `Content-Type`, `Content-Disposition` và security response headers.
10. **Chốt contract.** Viết tài liệu media type mà client được phép gửi/nhận và đưa test vào CI.

### Checklist ngắn

- [ ] Mặc định dùng `Accept`, không tự suy đoán từ URL extension.
- [ ] Có `produces` khi endpoint cần cố định media type response.
- [ ] Có `consumes` cho request body cần định dạng xác định.
- [ ] Nếu bật `?format=`, đăng ký media type và giới hạn giá trị cho phép.
- [ ] Không kích hoạt suffix pattern matching/path-extension negotiation chỉ vì client thiếu `Accept`.
- [ ] Test đủ 200, 406, 415 và các trường hợp path/query không hợp lệ.
- [ ] Không coi thêm converter là cho phép tự động mọi output format.
- [ ] Kiểm tra `Vary`, cache key và response security headers.
- [ ] Dùng `WebMvcConfigurer` thay vì bật `@EnableWebMvc` không cần thiết trong Spring Boot.

## 17. Kết luận

**Content negotiation là hợp đồng về media type, không phải cơ chế đoán file format.** Trong Spring MVC, cách an toàn và dễ bảo trì nhất cho REST API là dựa trên `Accept`, khai báo `produces`/`consumes` đúng với định dạng thực sự hỗ trợ và có converter tương ứng. Không bật suy luận theo phần mở rộng URL. Nếu cần `format` query parameter, chỉ mở với các mapping đã đăng ký và kiểm thử các trường hợp xung đột/không được hỗ trợ.

Cần nhớ:

- `Accept` chọn **response**; `Content-Type` của request mô tả **input**.
- `406` liên quan output representation không phù hợp; `415` liên quan input media type.
- `ContentNegotiationManager` phân giải media type mà client yêu cầu, không tự tạo converter.
- `@ResponseBody`/REST dùng `HttpMessageConverter`; MVC view dùng `ViewResolver`/`View` tương ứng.
- Suffix path inference tạo rủi ro mơ hồ route/security; query allowlist hoặc route tường minh an toàn hơn.

## 18. Tài liệu tham khảo

- Spring Framework 6.2 — Content Types và Content Negotiation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/content-negotiation.html
- Spring Framework — Request Mapping, produces/consumes, suffix match và RFD: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — ContentNegotiationConfigurer Javadoc: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/servlet/config/annotation/ContentNegotiationConfigurer.html
- Spring Boot 3.5 — Servlet Web Applications (MVC content negotiation): https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 Release Notes — default-content-types property: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes
- RFC 9110 — HTTP Semantics, Accept, Content-Type và status codes: https://www.rfc-editor.org/rfc/rfc9110
