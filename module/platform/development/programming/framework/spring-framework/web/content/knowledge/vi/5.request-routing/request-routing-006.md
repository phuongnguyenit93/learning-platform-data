# Xử lý HEAD, OPTIONS và phân biệt lỗi HTTP 404, 405, 406, 415 trong Spring MVC

## Mục tiêu và phạm vi

Sau bài này, bạn có thể giải thích vì sao một phương thức điều khiển dùng `@GetMapping` thường xử lý được `HEAD`, đọc header `Allow` trong phản hồi `OPTIONS`, đồng thời xác định chính xác một yêu cầu sai ở **đường dẫn**, **HTTP method**, **kiểu dữ liệu phản hồi** hay **kiểu dữ liệu gửi lên**. Ví dụ sử dụng Spring MVC trên Servlet stack, Java 17+ và cú pháp Spring Framework 6+/Spring Boot 3.x. Các quy tắc HTTP là nền tảng; phần body lỗi mặc định có thể khác giữa các phiên bản, cấu hình Spring Boot, bộ lọc và máy chủ.

## 1. Luồng chọn handler: nơi phát sinh bốn mã lỗi

Với `@RequestMapping`, Spring MVC chọn handler dựa trên nhiều điều kiện. Để chẩn đoán, hãy kiểm tra theo câu hỏi nghiệp vụ sau:

1. **Đường dẫn:** Có controller/resource nào nhận URL này không? Nếu không có tài nguyên tương ứng, kết quả thường là `404 Not Found`.
2. **Phương thức HTTP:** Đường dẫn phù hợp nhưng không hỗ trợ `GET`, `POST`, `PUT`… mà client gửi? Với mapping controller điển hình, kết quả là `405 Method Not Allowed`; xem header `Allow` để biết phương thức được hỗ trợ.
3. **`Content-Type` của request:** Endpoint yêu cầu nhận JSON nhưng client gửi `text/plain`? Có thể là `415 Unsupported Media Type`.
4. **`Accept` của request:** Client chỉ chấp nhận XML nhưng endpoint chỉ cung cấp JSON? Có thể là `406 Not Acceptable`.

Đây là **mô hình phân loại**, không phải cam kết Spring luôn xét tất cả điều kiện theo thứ tự 1→4; việc chọn mapping, message converter, handler ngoại lệ và filter có thể làm thay đổi mã lỗi xuất hiện khi một request vi phạm đồng thời nhiều điều kiện. Trong xử lý tiêu chuẩn của `RequestMappingInfoHandlerMapping`, các điều kiện `method`, `consumes` và `produces` được xem xét khi không tìm thấy mapping khớp hoàn toàn. Ngoài ra, body request/response còn có thể bị từ chối ở giai đoạn đọc/ghi bằng `HttpMessageConverter`.

| Mã | Tên chuẩn | Câu hỏi chẩn đoán | Dấu hiệu thường gặp |
| --- | --- | --- | --- |
| `404` | Not Found | URL/resource có tồn tại hay được định tuyến không? | Sai đường dẫn, thiếu tiền tố, resource không tìm thấy |
| `405` | Method Not Allowed | URL đúng nhưng method sai? | `POST` vào endpoint chỉ khai báo `GET`; phản hồi có `Allow` |
| `406` | Not Acceptable | Server có representation nào hợp lệ với `Accept` không? | Client đòi `application/xml`, server chỉ `produces = application/json` |
| `415` | Unsupported Media Type | Body client gửi có `Content-Type` mà endpoint/decoder nhận được không? | Gửi `text/plain` vào endpoint `consumes = application/json` |

Hai header rất dễ nhầm:

- `Content-Type` mô tả **loại dữ liệu trong body được gửi** (request) hoặc **loại dữ liệu trong body được trả về** (response).
- `Accept` mô tả **các loại dữ liệu client có thể nhận về**; ví dụ `Accept: application/json`. Nó không nói body request là JSON.
- `consumes` là điều kiện trên kiểu dữ liệu **đầu vào**, thường áp dụng cho POST/PUT/PATCH có body. `produces` là điều kiện trên kiểu dữ liệu **đầu ra**. Spring có thể sử dụng content negotiation và `HttpMessageConverter` ngay cả khi không khai báo hai thuộc tính này.

## 2. HTTP HEAD: lấy metadata, không nhận response body

Theo ngữ nghĩa HTTP, `HEAD` giống `GET` ở chỗ hỏi thông tin về resource nhưng **response không chứa message body**. Header của phản hồi `HEAD` nên tương ứng với `GET`, chẳng hạn `Content-Type`, `ETag`, `Last-Modified` hoặc `Content-Length` khi server có thể xác định. Không nên mặc định mọi server đều trả `Content-Length` hoặc mọi header giống hệt `GET`.

Trong Spring MVC, `@GetMapping` và `@RequestMapping(method = RequestMethod.GET)` **tự hỗ trợ HEAD**. Thông thường bạn không phải viết `@RequestMapping(method = RequestMethod.HEAD)` riêng; Spring/Servlet xử lý việc không gửi body. Điều này có hệ quả:

- Client gửi `HEAD /api/items/5` có thể đi qua cùng controller logic với `GET /api/items/5`; việc đọc database, tính toán hoặc lỗi nghiệp vụ vẫn có thể xảy ra.
- `HEAD` **không tự làm GET rẻ hơn**. Với dữ liệu tạo ra tốn kém, cần cân nhắc caching, metadata hoặc handler `HEAD` riêng khi có lý do đo được.
- `HEAD` đúng nghĩa phải không có response body. Không suy luận rằng HEAD trả `204 No Content`: một HEAD thành công của GET thường có **status 200**, chỉ khác ở việc không gửi body.
- Dùng `curl -I` (hoặc `curl --head`) để thử; tránh `curl -X HEAD` vì khi ép method thủ công, `curl` có thể vẫn đợi body theo cách xử lý khác với chế độ `--head`.

Ví dụ minh họa:

```http
GET /api/items/5 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":5,"name":"Pen"}
```

Cùng tài nguyên với `HEAD`:

```http
HEAD /api/items/5 HTTP/1.1
Host: localhost:8080
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

Phần ví dụ HTTP cố tình chỉ nêu các header cần thiết; nhiều máy chủ có thể thêm `Content-Length`, `Date` và các header khác. **Không có JSON/body** sau response HEAD.

Khi cần hành vi riêng, có thể khai báo mapping tường minh cho `HEAD`, nhưng phải kiểm tra tính tương thích với `GET` và không dùng phép viết phản hồi HEAD để tạo hiệu ứng phụ bất ngờ. Tránh coi HEAD là cách kiểm tra URL tồn tại hoàn toàn miễn phí.

## 3. HTTP OPTIONS: hỏi các phương thức được hỗ trợ

`OPTIONS` hỏi khả năng giao tiếp của tài nguyên. Trong Spring MVC, nếu chưa định nghĩa handler OPTIONS riêng, framework thường tự phản hồi bằng header `Allow` được tổng hợp từ các `@RequestMapping` cùng khớp URL. Mapping chỉ khai báo `GET` thường hỗ trợ `GET` và `HEAD`; `OPTIONS` có thể xuất hiện trong `Allow` do xử lý tự động. Nếu một `@RequestMapping` không giới hạn method, danh sách mặc định có thể rất rộng (`GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS`), vì vậy **nên khai báo method tường minh** cho API.

Ví dụ endpoint chỉ hỗ trợ GET:

```http
OPTIONS /api/items/5 HTTP/1.1
Host: localhost:8080
```

Phản hồi điển hình:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, OPTIONS
```

Thứ tự các method trong `Allow` không phải điều bạn nên dựa vào khi kiểm thử; tùy handler và môi trường, giá trị có thể thay đổi. Nếu endpoint hỗ trợ thêm PUT/DELETE, `Allow` sẽ phản ánh cấu hình mapping tương ứng.

**OPTIONS thông thường khác với CORS preflight**:

- Một preflight của trình duyệt cũng là `OPTIONS`, nhưng thường có `Origin` và `Access-Control-Request-Method`, có thể thêm `Access-Control-Request-Headers`.
- CORS preflight hỏi: “Origin này có được phép gọi method/header như dự kiến không?”; phản hồi được kiểm soát bởi cấu hình CORS, các header như `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
- Một API có mapping `POST` không có nghĩa trình duyệt từ origin khác được phép POST. CORS hay Spring Security có thể chặn preflight với `403` hoặc phản hồi khác trước khi tới controller.
- Header `Allow` của HTTP không thay thế `Access-Control-Allow-Methods`. Nếu debug lỗi CORS, kiểm tra cấu hình CORS/filter/security chứ không chỉ đọc `@RequestMapping`.

Ví dụ preflight:

```http
OPTIONS /api/items HTTP/1.1
Origin: https://frontend.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Đây là yêu cầu CORS; **không được giả định** nó thành công khi chưa cấu hình origin, method và header được phép.

## 4. Ví dụ controller Java 17+ để tự thử

Dùng một ứng dụng Spring Boot 3.x đã có dependency `spring-boot-starter-web`. Đặt lớp sau tại `src/main/java/com/example/demo/ItemController.java`; package phải nằm trong phạm vi component scan của lớp `@SpringBootApplication`. Không cần endpoint HEAD hoặc OPTIONS riêng cho bài này.

```java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Item find(@PathVariable("id") long id) {
        return new Item(id, "Pen");
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Item> create(@RequestBody Item item) {
        return ResponseEntity.status(HttpStatus.CREATED).body(item);
    }

    public record Item(long id, String name) {}
}
```

Đọc mapping:

- `GET /api/items/5` trả JSON cho bản ghi `Item(5, "Pen")`.
- `HEAD /api/items/5` được hỗ trợ nhờ mapping GET.
- `OPTIONS /api/items/5` thường tự trả `Allow` cho resource đó.
- `POST /api/items` nhận **request JSON** và trả **response JSON** với status `201 Created`. Đây chỉ là demo echo dữ liệu; không lưu vào database.
- `PUT /api/items/5` sai method. `GET /api/items/missing/child` sai đường dẫn. `Accept: application/xml` không phù hợp với GET chỉ xuất JSON. `POST /api/items` có `Content-Type: text/plain` không phù hợp với POST chỉ nhận JSON.

Nếu tạo dự án mới, tối thiểu cần một lớp `@SpringBootApplication` có hàm `main`, Java 17+, dependency Web, Maven/Gradle phù hợp. Trong dự án Maven có wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell có thể chạy `.\mvnw.cmd spring-boot:run`. Port mặc định là `8080` nếu chưa đổi `server.port`. Mã controller trên là lớp **đầy đủ có thể biên dịch trong dự án Spring Boot** đã cấu hình dependency; một tệp Java độc lập không thể `javac` mà thiếu Spring libraries.

## 5. Thực hành với curl: sáu tình huống phân biệt

Các lệnh dưới đây chạy khi ứng dụng đã khởi động trên `localhost:8080`. Header khác có thể xuất hiện tùy cấu hình; tập trung vào **HTTP status**, `Allow`, `Content-Type` và việc có/không có body.

**(A) GET thành công, 200:**

```bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/5
```

Body JSON dự kiến:

```json
{"id":5,"name":"Pen"}
```

**(B) HEAD thành công, 200:**

```bash
curl -I http://localhost:8080/api/items/5
```

Kiểm tra status và response headers; không có body JSON. `Content-Length` có thể được cung cấp tùy cơ chế xử lý và máy chủ.

**(C) OPTIONS, kiểm tra Allow:**

```bash
curl -i -X OPTIONS http://localhost:8080/api/items/5
```

Dự kiến `200 OK` với `Allow` gồm `GET`, `HEAD` (thông thường có `OPTIONS`). Nếu dùng `OPTIONS` kèm header CORS, đó là phép thử khác.

**(D) 404: URL không khớp:**

```bash
curl -i http://localhost:8080/api/items/5/unknown
```

Dự kiến `404 Not Found` vì không có mapping phù hợp đường dẫn này. Spring Boot có thể định tuyến yêu cầu sang bộ xử lý static resource trước khi kết luận không tồn tại; kết quả cuối vẫn có thể là 404 nhưng exception bên trong khác.

**(E) 405: URL đúng, HTTP method sai:**

```bash
curl -i -X PUT http://localhost:8080/api/items/5
```

Dự kiến `405 Method Not Allowed`; theo chuẩn HTTP, response 405 phải có header `Allow` liệt kê phương thức hiện được hỗ trợ cho tài nguyên. Ở controller demo, đó là GET/HEAD và thường OPTIONS. Đừng “sửa” 405 bằng cách đổi đường dẫn khi đường dẫn đã đúng; kiểm tra method.

**(F) 406: Client chỉ chấp nhận XML, server chỉ sinh JSON:**

```bash
curl -i -H "Accept: application/xml" http://localhost:8080/api/items/5
```

Dự kiến `406 Not Acceptable` vì mapping GET khai báo `produces = application/json`. Nếu gửi `Accept: */*` hoặc `Accept: application/json`, representation JSON có thể được chọn. Nếu thêm endpoint hỗ trợ XML hoặc thay cấu hình negotiation/converter, hành vi có thể khác.

**(G) 415: Client gửi loại body sai:**

```bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: text/plain" \
  --data "hello"
```

Dự kiến `415 Unsupported Media Type` vì POST khai báo `consumes = application/json`. Dùng request JSON hợp lệ:

```bash
curl -i http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"id":9,"name":"Notebook"}'
```

Dự kiến `201 Created` và body:

```json
{"id":9,"name":"Notebook"}
```

Nếu chạy lệnh shell nhiều dòng: cú pháp `\` là nối dòng cho bash, zsh; với PowerShell có thể viết toàn bộ `curl` trên **một dòng** và gọi `curl.exe` để tránh alias `Invoke-WebRequest` ở môi trường Windows PowerShell cũ. Tránh biến ví dụ minh họa thành khẳng định rằng tất cả môi trường cùng trả một JSON lỗi: chỉ mã HTTP và các header bắt buộc/được định nghĩa là trọng tâm.

## 6. Khi nào Spring MVC trả các lỗi này?

### 404 Not Found

Nếu không có handler/resource phù hợp, Spring MVC hoặc tầng phục vụ tài nguyên có thể dẫn đến 404. Trong các phiên bản Spring mới, handler static resource có thể gây `NoResourceFoundException`; trường hợp không tìm thấy handler có thể dùng `NoHandlerFoundException` tùy cấu hình. Không nên suy ra lớp exception cụ thể chỉ từ status.

Các nguyên nhân thực tế: sai `context-path`, thiếu prefix `@RequestMapping` ở class, sai trailing slash/case, proxy rewrite URL, định tuyến path variable khác dự kiến, file static không tồn tại. Nếu đường dẫn tồn tại ở service nhưng 404 phía gateway, cần kiểm tra cả reverse proxy.

### 405 Method Not Allowed

Đường dẫn khớp với controller mapping nhưng HTTP method không được hỗ trợ. Spring MVC thường biểu diễn trường hợp này bằng `HttpRequestMethodNotSupportedException`. Kiểm tra `Allow`, `@GetMapping`/`@PostMapping` và method thực tế ở network tab; đôi khi HTML form/browser hoặc HTTP client đã thay method. Đừng quên `HEAD` ngầm khi có GET.

Một URL “có tồn tại” theo ứng dụng không đảm bảo mọi loại request tới URL đó đều nhận 405; filters, security, tài nguyên tĩnh hoặc điều kiện mapping khác có thể can thiệp.

### 406 Not Acceptable

Client yêu cầu representation qua `Accept` nhưng server không thể cung cấp loại đó. Spring MVC có thể phát sinh `HttpMediaTypeNotAcceptableException` tại bước chọn mapping `produces` hoặc negotiation/conversion khi ghi response. Kiểm tra `Accept`, `produces`, các message converter đã đăng ký và kiểu object trả về. Trả object Java không tự đảm bảo server hỗ trợ mọi định dạng; ví dụ XML đòi hỏi cấu hình/converter phù hợp.

Ví dụ: `Accept: application/xml` không đồng nghĩa với “body request là XML”. Đây là yêu cầu **response XML**.

### 415 Unsupported Media Type

Request mang `Content-Type` mà mapping `consumes` hoặc message converter đọc body không hỗ trợ. Spring MVC có thể phát sinh `HttpMediaTypeNotSupportedException`. Kiểm tra header `Content-Type` thực gửi, `consumes` và khả năng converter đọc loại dữ liệu đó vào kiểu `@RequestBody`. Trường hợp body là JSON nhưng gắn nhãn `text/plain` vẫn có thể bị 415 trước khi parse.

Ngược lại, nếu header `Content-Type: application/json` đã đúng nhưng **JSON sai cú pháp**, lỗi thường là **400 Bad Request**, ví dụ `HttpMessageNotReadableException`, chứ không phải 415. Không nhầm với `406`: 415 hỏi **server đọc gì từ client**, 406 hỏi **client chấp nhận gì từ server**.

## 7. Bảng chẩn đoán nhanh với cùng bộ endpoint

| Request | Điều kiện chính | Status kỳ vọng ở demo |
| --- | --- | --- |
| `GET /api/items/5`, `Accept: application/json` | Path, method, output phù hợp | `200` |
| `HEAD /api/items/5` | GET mapping tự hỗ trợ HEAD | `200`, không body |
| `OPTIONS /api/items/5` | Query các HTTP method hỗ trợ | Thường `200`, có `Allow` |
| `GET /api/items/5/unknown` | Không có mapping/resource phù hợp | `404` |
| `PUT /api/items/5` | Path có GET nhưng không có PUT | `405`, có `Allow` |
| `GET /api/items/5`, `Accept: application/xml` | Không đáp ứng kiểu response | `406` |
| `POST /api/items`, `Content-Type: text/plain` | Không nhận kiểu request body | `415` |
| `POST /api/items`, `Content-Type: application/json`, JSON lỗi | Kiểu media được nhận nhưng cú pháp body sai | Thường `400` |
| `POST /api/items`, JSON hợp lệ và `Accept: application/json` | Input/output phù hợp | `201` |

Vì `OPTIONS` còn phục vụ preflight và lỗi có thể được tùy chỉnh bởi `@ControllerAdvice`, bảng này mô tả môi trường demo không thêm security/CORS filters đặc biệt.

## 8. Kiểm thử tự động bằng MockMvc

Với dự án Spring Boot đã cài `spring-boot-starter-test`, đặt tệp dưới `src/test/java/com/example/demo/HttpMethodRoutingTest.java`. Test sử dụng controller demo và môi trường Spring Boot chứa nó. Các assertion tập trung vào status và header cốt lõi; không phụ thuộc vào JSON lỗi do Boot tạo ra.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpMethodRoutingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void headUsesGetMappingWithoutBody() throws Exception {
        mvc.perform(head("/api/items/5"))
            .andExpect(status().isOk())
            .andExpect(content().string(""));
    }

    @Test
    void optionsReportsSupportedMethods() throws Exception {
        mvc.perform(options("/api/items/5"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void missingPathReturns404() throws Exception {
        mvc.perform(get("/api/items/5/unknown"))
            .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(put("/api/items/5"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string(
                HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void incompatibleAcceptReturns406() throws Exception {
        mvc.perform(get("/api/items/5")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void incompatibleContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Chạy `./mvnw test` (Windows: `.\mvnw.cmd test`). Nếu dự án đã có Spring Security hoặc cấu hình CORS riêng, hãy cấu hình MockMvc/test security phù hợp; những bộ lọc có thể trả `401`, `403` hoặc điều hướng khác trước khi logic controller chạy.

## 9. Debug thực tế và lỗi dễ mắc

1. **Xác nhận request thực nhận**: method, URL/path đã qua reverse proxy, query, `Content-Type`, `Accept`, body. Đặc biệt công cụ gọi API có thể tự thêm `Accept: */*` hoặc thay `Content-Type` khi chọn form-data.
2. **Đọc mapping đã đăng ký**: kiểm tra annotation ở class và method; Spring Boot Actuator `/actuator/mappings` (nếu có dependency và được bật/expose) giúp xem mapping thực. Chỉ mở endpoint quản trị theo chính sách an toàn ứng dụng.
3. **Dùng ma trận request tối thiểu**: cùng URL, đổi từng thứ một: method → `Accept` → `Content-Type`. Nếu thay nhiều header/method cùng lúc, mã lỗi hiện ra có thể che lỗi khác.
4. **Nhìn response status và headers trước body**: `Allow` hỗ trợ điều tra 405/OPTIONS; response `Content-Type` cho biết server trả loại nội dung gì. Body thông báo lỗi có thể bị cấu hình bằng `ProblemDetail`, error controller hay gateway.
5. **Tách CORS khỏi mapping**: xem `Origin`/`Access-Control-Request-Method` và chính sách CORS; preflight fail không đồng nghĩa controller không hỗ trợ method.
6. **Tách 415 khỏi JSON parse failure**: `415` là vấn đề media type; `400` thường là body sai định dạng/thiếu trường/chuyển đổi dữ liệu, tùy validation.
7. **Tách 404 khỏi 405**: 404 nghi path/resource; 405 nghi method. Nếu tất cả method đều 404, kiểm tra tiền tố route và deployment trước.
8. **Đừng dùng `@RequestMapping` không khai báo method tùy tiện**: nó có thể khiến `Allow` rộng ngoài ý định và làm API nhận những method không mong muốn.
9. **Tránh tùy chỉnh trả lỗi làm mất header bắt buộc**: khi bắt `HttpRequestMethodNotSupportedException` để chuẩn hóa JSON lỗi, vẫn phải giữ `Allow`. Spring MVC đã có `DefaultHandlerExceptionResolver` và `ResponseEntityExceptionHandler`; ưu tiên giữ semantics chuẩn khi viết `@ControllerAdvice`.
10. **Không đoán “404 luôn là NoHandlerFoundException”**: resource handler, path matching, version framework và custom error handler có thể khác. Dùng log và mapping để truy ra bước lỗi thật.

## 10. Tự kiểm tra kiến thức

- `HEAD /api/items/5` đi vào `@GetMapping` được không? **Có**, Spring MVC hỗ trợ HEAD ngầm; phản hồi không có body, nhưng handler vẫn có thể chạy công việc.
- `OPTIONS` trả header gì để báo những method được hỗ trợ? **`Allow`**. Với CORS preflight phải xét thêm những header `Access-Control-Allow-*` và cấu hình origin.
- URL có mapping GET nhưng gọi PUT: **405** và xem `Allow`. URL không có mapping/resource: thường **404**.
- GET chỉ `produces = application/json` nhưng request `Accept: application/xml`: **406**.
- POST `consumes = application/json` nhưng request `Content-Type: text/plain`: **415**.
- POST gửi `Content-Type: application/json` mà body `{bad json}`: thông thường **400**, vì media type đúng nhưng JSON không đọc được.
- `Accept` và `Content-Type` có thay thế cho nhau được không? **Không**; một bên mô tả dữ liệu client muốn **nhận**, bên kia mô tả body **đang gửi** (trong request).

## Tài liệu tham khảo

- Spring Framework — Mapping Requests (gồm HEAD, OPTIONS, `consumes`, `produces`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Error Responses và `ResponseEntityExceptionHandler`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MVC Exception Resolvers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- HTTP Semantics (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110.html
