# Cấu trúc yêu cầu và phản hồi HTTP: phương thức, URI, header và nội dung

## 1. HTTP trao đổi thông tin như thế nào?

HTTP (Hypertext Transfer Protocol) là giao thức tầng ứng dụng cho phép client (trình duyệt, ứng dụng di động, `curl`, chương trình Java...) giao tiếp với server qua mô hình **request → response**. Client gửi yêu cầu chứa hành động muốn thực hiện và thông tin cần thiết; server xử lý rồi trả trạng thái, metadata và có thể có nội dung. Trong Spring Boot Web, HTTP là ranh giới giữa client và các endpoint do ứng dụng công bố.

Một trao đổi điển hình:

~~~text
Client                                   Server (Spring Boot)
  | -- HTTP request ---------------------> |
  |    method + URI + headers + body      | nhận, định tuyến, xử lý
  | <---------------------- HTTP response |
       status + headers + body
~~~

HTTP được coi là **stateless** về mặt giao thức: bản thân mỗi request không mặc nhiên mang trạng thái phiên trước đó. Ứng dụng có thể duy trì đăng nhập hoặc giỏ hàng bằng cookie, token, session hay cơ sở dữ liệu, nhưng phải có cơ chế truyền/tra cứu trạng thái rõ ràng.

Các ví dụ dạng văn bản bên dưới minh họa **HTTP/1.1**. HTTP/2 và HTTP/3 vẫn có các khái niệm method, URI, status, header và content tương ứng, nhưng truyền chúng bằng frame nhị phân (và pseudo-header), không gửi nguyên dòng mở đầu dạng văn bản giống HTTP/1.1.

## 2. Một HTTP request gồm những phần nào?

Ở HTTP/1.1, hình dạng logic phổ biến là:

~~~http
METHOD /path?query HTTP/1.1
Host: example.test
Header-Name: header value

optional request body
~~~

Giữa các dòng trên đường truyền là CRLF (`\r\n`), và **một dòng trống** phân cách phần header với phần body (nếu có). Bốn yếu tố cần phân biệt:

| Thành phần | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| **Method** | Client muốn làm gì với tài nguyên? | `GET`, `POST`, `PUT` |
| **URI / request target** | Request nhắm đến tài nguyên nào? | `/api/books/42?lang=vi` |
| **Headers** | Metadata và chỉ dẫn giao tiếp là gì? | `Accept`, `Content-Type`, `Authorization` |
| **Body / content** | Dữ liệu nội dung đi kèm là gì? | JSON, form, tệp hoặc byte nhị phân |

Dòng mở đầu HTTP/1.1 gồm method, request target và phiên bản giao thức. Ví dụ `GET /api/books/42 HTTP/1.1`. Dòng này không chứa status code: status xuất hiện ở **response**.

### Phương thức HTTP (method)

| Method | Mục đích thông thường | Safe? | Idempotent? |
| --- | --- | --- | --- |
| `GET` | Lấy biểu diễn tài nguyên; không chủ ý thay đổi trạng thái server | Có | Có |
| `HEAD` | Lấy thông tin tương tự GET, nhưng response không có body | Có | Có |
| `POST` | Gửi dữ liệu để server xử lý, thường tạo tài nguyên/hành động | Không | Không bảo đảm |
| `PUT` | Tạo/thay thế trạng thái tài nguyên tại URI đích theo biểu diễn gửi lên | Không | Có |
| `PATCH` | Yêu cầu áp dụng thay đổi một phần | Không | Không bảo đảm |
| `DELETE` | Yêu cầu xóa liên kết/trạng thái tài nguyên tại URI đích | Không | Có |
| `OPTIONS` | Hỏi các tùy chọn giao tiếp; thường gặp trong CORS preflight | Có | Có |

**Safe** nghĩa là hành động được yêu cầu về mặt ngữ nghĩa không chủ đích làm thay đổi trạng thái ứng dụng; server vẫn có thể ghi log hoặc thống kê. **Idempotent** nghĩa là thực hiện cùng request nhiều lần có **hiệu ứng dự định lên trạng thái server** giống như thực hiện một lần, không có nghĩa các lần luôn trả cùng status hay cùng body. Ví dụ: DELETE lần đầu có thể trả 204, lần sau 404 nhưng phương thức vẫn idempotent; PUT cùng biểu diễn không được tự động tạo thêm một bản ghi mỗi lần.

Không suy ra CRUD một cách máy móc: POST có thể kích hoạt xử lý không tạo tài nguyên; PATCH *có thể* được thiết kế idempotent nhưng không được bảo đảm bởi chính method. Với GET, tránh gắn hành động gây thay đổi trạng thái nghiệp vụ như thanh toán, xóa bản ghi. Body trong GET không có ngữ nghĩa chung được xác định và có thể bị server hoặc trung gian từ chối; thông thường dùng URI/query để biểu đạt truy vấn.

### URI, URL và request target

Ví dụ URL:

~~~text
https://api.example.test:8443/api/books/42?lang=vi&page=2#reviews
|https| |--- authority ----| |-- path -----| |--- query -----| fragment
~~~

- **Scheme** (`https`) cho biết cách truy cập; HTTPS là HTTP truyền trên kết nối được bảo vệ bằng TLS.
- **Authority** gồm host (và có thể có port). Host + port xác định đích mạng; cổng mặc định thường là 443 cho HTTPS, 80 cho HTTP.
- **Path** (`/api/books/42`) định vị tài nguyên trong ứng dụng. Ở Spring MVC, pattern `/api/books/{id}` có thể gắn với biến `id=42`.
- **Query** (sau `?`) cung cấp cặp tham số như `lang=vi&page=2`; dấu `&` phân tách tham số. Query có thể lặp key, có thể thiếu giá trị và thứ tự đôi khi có ý nghĩa theo hợp đồng API.
- **Fragment** (`#reviews`) phục vụ client điều hướng trong tài liệu; **không được gửi lên server trong HTTP request target thông thường**.

Trong HTTP/1.1 tới origin server, request line thường chỉ chứa path và query: `GET /api/books/42?lang=vi HTTP/1.1`; host được xác định bằng `Host: api.example.test:8443`. Một forward proxy có thể nhận dạng request target khác (chẳng hạn absolute-form). Ở HTTP/2/3, các pseudo-header như `:method`, `:scheme`, `:authority`, `:path` truyền thông tin tương đương.

**Path và query không giống body.** Path nhận diện tài nguyên, query chọn lọc/điều chỉnh cách truy xuất, còn body mang biểu diễn hoặc dữ liệu cần xử lý. Ký tự đặc biệt trong URI phải mã hóa đúng kiểu percent-encoding (ví dụ khoảng trắng là `%20` trong URI); không tự ghép chuỗi từ đầu vào chưa mã hóa. URI có thể xuất hiện trong history, proxy log và hệ thống giám sát, vì vậy không đặt mật khẩu, access token hay dữ liệu bí mật trong query.

## 3. HTTP headers: metadata và điều kiện xử lý

Header thường là các dòng `Name: value`. **Tên header không phân biệt chữ hoa/chữ thường**; giá trị có ngữ nghĩa tùy header. Không đánh đồng header với dữ liệu body.

| Header | Chiều thường gặp | Ý nghĩa |
| --- | --- | --- |
| `Host` | Request HTTP/1.1 | Host đích; bắt buộc trong request HTTP/1.1 |
| `Accept` | Request | Các media type mà client chấp nhận ở response, ví dụ `application/json` |
| `Content-Type` | Request/response có content | Media type của **body đang gửi**, ví dụ `application/json` hoặc `text/plain; charset=UTF-8` |
| `Authorization` | Request | Thông tin xác thực, ví dụ `Bearer ...`; không ghi token thật vào log |
| `Cookie` | Request | Cookie client gửi; có thể chứa mã định danh phiên |
| `Set-Cookie` | Response | Server yêu cầu client lưu/cập nhật cookie cùng thuộc tính bảo vệ |
| `Location` | Response | URI của tài nguyên mới hoặc đích chuyển hướng, theo status |
| `Cache-Control` | Cả hai | Chính sách cache, ví dụ `no-store` hoặc `max-age=60` |
| `ETag` / `If-None-Match` | Response / request | Validator và điều kiện để lấy lại biểu diễn hiệu quả |
| `Content-Length` | Cả hai khi phù hợp | Số **byte** content ở dạng wire framing tương ứng, không phải số ký tự Unicode |
| `Origin` | Request | Origin của client; thường xuất hiện trong giao tiếp trình duyệt/CORS |
| `Access-Control-Allow-Origin` | Response | Khai báo origin được phép truy cập response theo cơ chế CORS |

Phân biệt hai header dễ nhầm:

~~~http
POST /api/books HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
~~~

`Content-Type: application/json` nói rằng **client gửi JSON**; `Accept: application/json` nói rằng **client muốn nhận JSON**. Nếu server không hỗ trợ kiểu nội dung request thì có thể trả **415 Unsupported Media Type**; nếu không tạo được biểu diễn đáp ứng `Accept` thì có thể trả **406 Not Acceptable**. Cách chọn lỗi phụ thuộc hợp đồng API và framework.

Không nên giả định tất cả header do client gửi đều đáng tin, bao gồm `X-Forwarded-*` (phải cấu hình đúng proxy tin cậy). Header `Authorization` không tự xác thực người dùng nếu ứng dụng chưa cấu hình security. CORS là chính sách của trình duyệt liên quan chia sẻ response giữa các origin, **không thay thế phân quyền API**.

## 4. Request body: nội dung được gửi đi

Body là chuỗi byte **không bắt buộc**. Tùy API, nó có thể chứa:

- JSON (`application/json`) cho cấu trúc đối tượng/mảng, ví dụ `{"name":"Lan","active":true}`;
- dữ liệu form (`application/x-www-form-urlencoded`) như `name=Lan&active=true`;
- multipart (`multipart/form-data; boundary=...`) để kết hợp trường và tệp;
- văn bản (`text/plain`), XML, hình ảnh hoặc dữ liệu nhị phân (`application/octet-stream`).

Body có định dạng gì phải dựa vào `Content-Type` và hợp đồng endpoint; không đoán JSON chỉ vì chuỗi trông giống JSON. `Content-Length` tính bằng byte sau mã hóa: một chữ tiếng Việt có thể chiếm nhiều byte trong UTF-8. HTTP/1.1 cũng có thể dùng framing `Transfer-Encoding: chunked` thay cho một `Content-Length` đã biết; HTTP/2/3 có framing riêng. Header, body và việc kết thúc message phải hợp lệ để server biết ranh giới dữ liệu. Không gửi đồng thời các chỉ dẫn framing mâu thuẫn.

Ví dụ request POST **HTTP/1.1 có độ dài body chính xác** (toàn bộ ký tự JSON ở đây thuộc ASCII):

~~~http
POST /api/books HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Content-Length: 28

{"name":"Lan","active":true}
~~~

Dòng trống trước ký tự `{` phân định header và body. Body gồm 28 byte ASCII; server phải đọc đúng byte length, sau đó mới chuyển JSON thành object Java theo cấu hình.

## 5. Một HTTP response gồm những phần nào?

Với HTTP/1.1, response có **status line**, headers, dòng trống và body tùy trường hợp:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/books/42
Content-Length: 36

{"id":42,"name":"Lan","active":true}
~~~

Ví dụ giả định POST ở mục trước tạo sách id 42. **201 Created** cho biết tài nguyên được tạo; `Location` chỉ đến tài nguyên mới và body trả về biểu diễn JSON. Trường `Content-Length` ở đây là 36 byte ASCII. Reason phrase `Created` chỉ mang tính diễn giải ở HTTP/1.1; ứng dụng dựa vào **mã trạng thái số**. HTTP/2/3 thể hiện status qua pseudo-header `:status`.

### Nhóm mã trạng thái

| Nhóm | Ý nghĩa | Ví dụ thực tế |
| --- | --- | --- |
| **1xx** | Thông tin trung gian | `100 Continue` |
| **2xx** | Xử lý thành công | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| **3xx** | Chuyển hướng/điều kiện cache | `301`, `302`, `304 Not Modified`, `307`, `308` |
| **4xx** | Vấn đề phía request | `400`, `401`, `403`, `404`, `405`, `409`, `415`, `422`, `429` |
| **5xx** | Server hoặc gateway không xử lý được | `500`, `502`, `503`, `504` |

Các phân biệt hữu ích:

- **200** thường kèm biểu diễn kết quả; **201** khi tạo tài nguyên, thường có `Location`; **202** nghĩa là đã nhận để xử lý nhưng xử lý chưa hoàn tất; **204** thành công nhưng **không có body**.
- **304 Not Modified** không gửi body biểu diễn mới; nó cho phép client tiếp tục dùng bản cache phù hợp.
- **400** request không hợp lệ; **401** thiếu/chưa đạt xác thực; **403** đã hiểu nhưng từ chối quyền; **404** không tìm thấy biểu diễn/tài nguyên theo hợp đồng API; **405** method không được hỗ trợ cho tài nguyên đó.
- **409** xung đột trạng thái hiện tại; **415** media type đầu vào không hỗ trợ; **422** nội dung hợp lệ về cú pháp/media type nhưng không xử lý được theo ngữ nghĩa; **429** vượt giới hạn request.
- **500** lỗi xử lý phía server; **502/503/504** thường liên quan gateway/dịch vụ hoặc tính sẵn sàng. Không trả 200 cho mọi kết quả lỗi chỉ vì body JSON có trường `error`.

Không phải response nào cũng có body. Response cho HEAD, 1xx, 204, 304 có quy tắc không mang content; 304 có thể chứa một số header cập nhật cache. Với redirect, client xem status kết hợp `Location`. Status code không cho biết toàn bộ ý nghĩa nếu thiếu hợp đồng endpoint và headers.

## 6. Đọc một trao đổi hoàn chỉnh từ đầu đến cuối

Giả sử client gửi:

~~~http
GET /api/books/42?verbose=true HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Request-Id: abc-123

~~~

Cách đọc theo thứ tự: `GET` là hành động truy xuất; `/api/books/42` chọn tài nguyên id 42; `verbose=true` là query; `Host` chỉ server; `Accept` yêu cầu JSON; `X-Request-Id` là header riêng theo hợp đồng ứng dụng. Request này không có body.

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":42,"name":"Lan","active":true}
~~~

Response minh họa trên **cố ý lược bỏ header framing** vì trình bày ở mức logic; khi truyền thực tế, server và phiên bản HTTP phải cung cấp framing hợp lệ. `200` là status, `Content-Type` mô tả JSON trả về, `Cache-Control` thông báo không lưu cache và body là dữ liệu. Dựa vào cặp request/response, ta có thể phân biệt lỗi định tuyến (method/path), thương lượng nội dung (headers), parse body và logic nghiệp vụ.

## 7. Liên hệ Spring Boot Web (Servlet / Spring MVC)

Đối với ứng dụng Spring Boot sử dụng `spring-boot-starter-web`, server HTTP nhúng tiếp nhận request rồi Spring MVC xử lý thông qua `DispatcherServlet`, lựa chọn handler dựa trên mapping, ràng buộc tham số và chuyển đổi content. Đây là **cách hiện thực HTTP trong framework**, không phải một định dạng HTTP riêng.

| Phần HTTP | Cách khai báo/đọc trong Spring MVC |
| --- | --- |
| Method và path | `@GetMapping`, `@PostMapping`, `@RequestMapping` |
| Path variable | `@PathVariable` |
| Query parameter | `@RequestParam` |
| Request header | `@RequestHeader` |
| Body JSON → Java | `@RequestBody` + message converter (thường là Jackson) |
| Response body Java → JSON | `@RestController` hoặc `@ResponseBody` |
| Status và response headers | `ResponseEntity`, `@ResponseStatus` |
| Media type đầu vào/đầu ra | `consumes`, `produces` |

Ví dụ chạy trong **dự án Spring Boot 3.x, Java 17+** đã có dependency `spring-boot-starter-web`. Tạo tệp `src/main/java/demo/http/HttpDemoApplication.java` đúng package và tên public class:

~~~java
package demo.http;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
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

@SpringBootApplication
public class HttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {
    private final Map<Long, BookView> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(100);

    BookController() {
        books.put(42L, new BookView(42L, "Lan", true));
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> find(
            @PathVariable long id,
            @RequestParam(defaultValue = "false") boolean verbose,
            @RequestHeader(name = "X-Debug", defaultValue = "false") boolean debug) {

        BookView book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .header("X-Debug-Enabled", Boolean.toString(verbose && debug))
                .body(book);
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(@RequestBody NewBook input) {
        if (input.name() == null || input.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.getAndIncrement();
        BookView created = new BookView(id, input.name(), input.active());
        books.put(id, created);

        return ResponseEntity.created(URI.create("/api/books/" + id))
                .body(created);
    }

    public record NewBook(String name, boolean active) {}
    public record BookView(long id, String name, boolean active) {}
}
~~~

Giải thích mối liên hệ:

1. `@GetMapping("/{id}")` nhận **GET /api/books/{id}**; `@PathVariable` lấy id từ path, `@RequestParam` đọc `?verbose=true`; `@RequestHeader` lấy `X-Debug` nếu có (mặc định false).
2. `ResponseEntity.ok()` xây response status 200 và header `X-Debug-Enabled` rồi xuất JSON qua converter. Không có id trong map thì trả 404.
3. `@PostMapping(consumes = "application/json")` giới hạn kiểu request body được chấp nhận. `@RequestBody NewBook` buộc Spring chuyển JSON thành Java record; sai JSON có thể dẫn đến 400, media type không phù hợp có thể dẫn đến 415.
4. `ResponseEntity.created(...)` chọn 201 và header `Location: /api/books/{id}`; body là record `BookView` được xuất thành JSON.
5. Map trong ví dụ chỉ lưu trong bộ nhớ để quan sát request/response: restart sẽ mất dữ liệu; ứng dụng thực tế cần lưu trữ, validation, security và xử lý lỗi theo hợp đồng API.

Trong dự án có Gradle wrapper và plugin Spring Boot được cấu hình, chạy `./gradlew bootRun` từ thư mục dự án (Windows PowerShell: `.\gradlew.bat bootRun`). Vì phụ thuộc Spring Boot và Jackson, **không** biên dịch riêng file này bằng `javac` thiếu classpath. Thử bằng `curl` trong bash/macOS/Linux:

~~~bash
curl -i "http://localhost:8080/api/books/42?verbose=true" \
  -H "Accept: application/json" \
  -H "X-Debug: true"

curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Mai","active":true}'

curl -i "http://localhost:8080/api/books/999"
~~~

Kỳ vọng quan sát: request GET đầu trả **200**, body `{"id":42,"name":"Lan","active":true}` và `X-Debug-Enabled: true`; POST đầu tiên kể từ khi khởi động trả **201**, `Location: /api/books/100` và body `{"id":100,"name":"Mai","active":true}`; GET id 999 trả **404**. Thứ tự headers, timestamp, header hệ thống và chi tiết thân lỗi mặc định có thể khác theo phiên bản/config. Lần POST tiếp theo tăng id; đây không phải cam kết về persistence hay API production.

## 8. Cách kiểm tra khi HTTP API hoạt động sai

Xem request và response như hai thông điệp riêng biệt, đối chiếu tuần tự:

1. **Method + path**: endpoint có đúng `GET/POST/PUT...` và URL không? `404` có thể do path sai; `405` thường do method sai trên path đã có handler.
2. **Path/query**: id, bộ lọc và ký tự percent-encoding có đúng không? Đừng nhầm `/books/42` với `/books?id=42` nếu API chỉ hỗ trợ một dạng.
3. **Headers**: `Content-Type` khớp body, `Accept` khớp response mong đợi, auth/session có được gửi hợp lệ không? Header tên không phân biệt hoa/thường.
4. **Body**: JSON có đúng cú pháp, đúng tên trường/kiểu dữ liệu, charset và giới hạn kích thước không? Dòng trống HTTP/1.1 có phân cách header/body không?
5. **Status + response headers**: kiểm tra status **trước** khi parse body; xem `Location` với 201/redirect, `Content-Type` với JSON và header cache khi cần.
6. **Trung gian**: load balancer/reverse proxy có rewrite path, thay đổi headers hoặc giới hạn body không? Chỉ tin các forwarded headers khi cấu hình proxy đúng.

Các lỗi phổ biến: dùng POST cho thao tác đọc mà không hiểu semantics; đặt dữ liệu nhạy cảm trong URI; đồng nhất `Accept` với `Content-Type`; nghĩ mọi request phải có body; cho rằng idempotent đồng nghĩa response giống nhau; đo `Content-Length` theo số ký tự; đọc fragment ở backend; trả 200 cho mọi lỗi; bỏ qua status và chỉ nhìn JSON body.

### Tự kiểm tra hiểu bài

**Tình huống A:** `GET /api/orders/7?detail=true`, `Accept: application/json`, không có body. Phần nào chọn tài nguyên, phần nào chỉnh biểu diễn, phần nào báo định dạng mong nhận? → Path chọn order 7; query `detail=true` điều chỉnh cách truy xuất; header `Accept` yêu cầu JSON nếu server hỗ trợ.

**Tình huống B:** Client gửi `Content-Type: text/plain` nhưng body là chuỗi JSON, endpoint Spring yêu cầu `consumes = application/json`. → Dù body *trông giống* JSON, server có thể trả **415** vì khai báo media type không phù hợp.

**Tình huống C:** Gửi DELETE cùng URI hai lần, lần đầu 204, lần sau 404. → Vẫn có thể đúng tính **idempotent** vì mục tiêu xóa tài nguyên đã đạt từ lần đầu; status hai lần không bắt buộc giống nhau.

**Tình huống D:** Response `204 No Content` nhưng client cố parse JSON body. → Client đang giả định sai; 204 không chứa response content, hãy dựa vào status.

## 9. Ghi nhớ trọng tâm

Một HTTP exchange có hai phía:

- **Request = method + URI + request headers + body (nếu có).** Method nêu hành động, URI xác định đích, headers nêu metadata/điều kiện, body truyền dữ liệu.
- **Response = status + response headers + body (nếu có).** Status cho kết quả ở mức giao thức, headers mô tả biểu diễn và chính sách, body trả nội dung.
- Trong Spring Boot Web, annotations ánh xạ các phần này sang handler Java và `ResponseEntity` ánh xạ kết quả xử lý ngược lại thành response. Hiểu đúng từng thành phần giúp thiết kế endpoint nhất quán và đọc lỗi từ network log chính xác hơn.
