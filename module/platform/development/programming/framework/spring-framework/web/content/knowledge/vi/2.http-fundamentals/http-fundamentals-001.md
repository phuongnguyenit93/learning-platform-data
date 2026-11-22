# Chu trình yêu cầu–phản hồi và cấu trúc một thông điệp HTTP

HTTP (Hypertext Transfer Protocol) là giao thức ứng dụng mà trình duyệt, ứng dụng di động, API client và máy chủ sử dụng để trao đổi yêu cầu và phản hồi. Trong lập trình Spring Web, hiểu HTTP là điều kiện để đọc đúng một request, chọn method, trả status code, xử lý header/body và xác định lỗi nằm ở client, mạng, bộ trung gian hay ứng dụng.

## 1. Mục tiêu học tập và mô hình tổng quan

Sau bài này, bạn cần có thể:
- Mô tả một vòng request–response từ lúc client gửi yêu cầu đến khi nhận được kết quả.
- Tách thông điệp HTTP/1.1 thành **start-line, headers, dòng trống phân cách và body (nếu có)**.
- Phân biệt request-target, method, status code, representation, media type, header và message body.
- Đọc một trao đổi HTTP thực tế, giải thích những gì Spring MVC nhận vào/trả ra.
- Hiểu ranh giới giữa cú pháp HTTP/1.1 dạng văn bản và cách mã hóa khác của HTTP/2, HTTP/3.

HTTP đi theo mô hình client khởi tạo yêu cầu; phía server gửi phản hồi tương ứng. Một kết nối có thể phục vụ nhiều trao đổi, nên **một request không đồng nghĩa một kết nối TCP mới**; HTTP/2 và HTTP/3 còn có thể xử lý nhiều stream đồng thời. HTTP thường được xem là **stateless về ngữ nghĩa**: mỗi request được xử lý theo thông tin đi kèm và trạng thái phía hệ thống, giao thức không tự buộc server nhớ một hội thoại ứng dụng giữa các lần gọi. Cookie, session hoặc token là cơ chế được ứng dụng dùng để duy trì ngữ cảnh.

Ví dụ một lần tra cứu sách:

~~~text
Client                       Server / Spring Web
  |   GET /books/42             |
  |----------------------------->|
  |                              | Đọc URI, method, headers
  |                              | Định tuyến và xử lý
  |   200 OK + JSON              |
  |<-----------------------------|
  | Hiển thị/sử dụng dữ liệu     |
~~~

Sơ đồ này mô tả trao đổi logic. Trên đường đi có thể có DNS, TLS, proxy, load balancer và servlet container; những tầng đó không phải các thành phần của một thông điệp HTTP.

## 2. Chu trình request–response từng bước

1. **Client xây request:** chọn method (ví dụ `GET`), đích (URI), query, các header cần thiết và body khi thích hợp. Chẳng hạn client có thể gửi `Accept: application/json` để yêu cầu một dạng biểu diễn JSON mà server hỗ trợ.
2. **Thiết lập kênh truyền:** client xác định endpoint, thường qua DNS nếu dùng hostname. Với HTTP/1.1 hoặc HTTP/2 thông dụng, kết nối dùng TCP; HTTPS còn có TLS. HTTP/3 truyền qua QUIC. Kết nối có thể được tái sử dụng.
3. **Truyền request:** client gửi thông tin theo phiên bản giao thức đã đàm phán. Một reverse proxy có thể nhận request rồi chuyển tiếp tới server ứng dụng.
4. **Server tiếp nhận và xử lý:** web server/servlet container nhận request; Spring MVC có thể chạy Filter, tìm controller phù hợp, chuyển đổi dữ liệu, gọi logic nghiệp vụ và tạo phản hồi.
5. **Server gửi response:** status code cho biết kết quả ở mức HTTP, headers cung cấp metadata và body chứa dữ liệu nếu loại response cho phép.
6. **Client diễn giải response:** xem status, headers, parse body theo media type, quyết định hiển thị dữ liệu, cache, điều hướng, đăng nhập lại hay báo lỗi.

Luồng request–response **không bảo đảm** request luôn tới ứng dụng hoặc response luôn thành công: DNS, TLS, timeout, proxy hay connection reset có thể làm trao đổi thất bại trước khi nhận được một HTTP status code.

## 3. Cấu trúc thông điệp HTTP/1.1

Khi quan sát cú pháp HTTP/1.1 truyền thống, một thông điệp có dạng:

~~~text
START-LINE\r\n
Header-Name: value\r\n
Another-Header: value\r\n
\r\n
[message body, nếu có]
~~~

Trong mẫu trên, ký hiệu `\r\n` biểu thị hai byte **CRLF** kết thúc mỗi dòng. Hai CRLF liên tiếp tạo dòng trống ngăn phần header và body. Dấu ngoặc vuông ở dòng body chỉ để diễn giải, không phải byte bắt buộc trong thông điệp. Header và body không bị giới hạn là dữ liệu văn bản thuần; body có thể là JSON, form, ảnh hoặc dữ liệu nhị phân. Header rỗng nghĩa là sau start-line có ngay một CRLF kết thúc vùng header (dù request HTTP/1.1 hợp lệ thông thường cần thông tin Host).

**Cảnh báo về phiên bản:** đây là cách biểu diễn *HTTP/1.x*. HTTP/2 và HTTP/3 giữ phần lớn ngữ nghĩa method, status, headers và body, nhưng dùng frame/binary encoding thay cho request/status start-line dạng text trên dây. Vì vậy không được khẳng định “mọi gói HTTP đều chứa dòng `GET /... HTTP/1.1`”. Trong HTTP/2/3, thông tin tương đương được biểu diễn qua pseudo-header như `:method`, `:path`, `:scheme`, `:authority`, và phản hồi qua `:status`; body nằm trong các data frame.

### 3.1. Request start-line

Một HTTP/1.1 request-line có hình thức:

~~~text
METHOD SP request-target SP HTTP-version CRLF
~~~

Ví dụ:

~~~http
GET /books/42?view=summary HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

- `GET` là **method**, diễn tả ý định lấy biểu diễn của tài nguyên.
- `/books/42?view=summary` là **request-target** ở dạng origin-form: path `/books/42` cộng query string `view=summary`. Fragment như `#intro` không được gửi trong request-target HTTP.
- `HTTP/1.1` là phiên bản trong request-line.
- `Host: api.example.test` xác định authority/virtual host cho request HTTP/1.1. Host header bắt buộc trong HTTP/1.1 và phải phù hợp authority của target URI.
- `Accept: application/json` cho biết client ưu tiên nhận nội dung theo media type JSON.

Request-target có các dạng khác cho một số tình huống, như absolute-form khi gửi qua forward proxy hoặc authority-form cho `CONNECT`. Đa số HTTP API thông thường dùng origin-form như ví dụ.

Phân biệt ba phần dễ nhầm:
- **Path** `/books/42` giúp định tuyến tới tài nguyên hoặc endpoint.
- **Query** `?view=summary` truyền tham số lựa chọn/bộ lọc; nó là một phần của URI, không phải body.
- **Body** là dữ liệu nằm sau dòng trống kết thúc headers; ví dụ JSON dùng để tạo đơn hàng.

### 3.2. Response status-line

HTTP/1.1 response bắt đầu bằng status-line:

~~~text
HTTP-version SP status-code SP [reason-phrase] CRLF
~~~

Ví dụ, một phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 15

{"status":"ok"}
~~~

- `HTTP/1.1` là phiên bản phản hồi.
- `200` là **status code** máy có thể diễn giải; `OK` là reason phrase để con người đọc, không nên dùng reason phrase làm cơ sở xử lý nghiệp vụ.
- `Content-Type: application/json` mô tả media type của representation trong body.
- `Content-Length: 15` cho biết body dài **15 byte**, không phải 15 chữ cái tiếng Việt hay số ký tự của JSON nói chung. Body ví dụ toàn ASCII nên 15 byte.
- Dòng trống đánh dấu kết thúc headers; `{"status":"ok"}` là body.

HTTP/2/3 không dùng reason phrase kiểu HTTP/1.1. API client nên dựa vào status code và nội dung/thỏa thuận ứng dụng, không cố khớp chuỗi `OK` hoặc `Not Found`.

### 3.3. Headers

Header gồm tên trường và giá trị, ví dụ `Content-Type: application/json`. Tên header **không phân biệt chữ hoa/chữ thường** ở mức ngữ nghĩa; `content-type` và `Content-Type` chỉ cùng một trường. HTTP/2 yêu cầu tên field được mã hóa chữ thường trong header block. Giá trị có cú pháp/ý nghĩa riêng theo từng trường, không nên tự động gộp mọi header trùng tên.

| Header | Vai trò thông dụng |
| --- | --- |
| `Host` | Chỉ định host/authority trong request HTTP/1.1. |
| `Accept` | Kiểu nội dung phản hồi client có thể tiếp nhận. |
| `Content-Type` | Kiểu media của phần nội dung đi kèm (request hoặc response). |
| `Content-Length` | Độ dài phần nội dung theo **byte**, trong các trường hợp được phép dùng. |
| `Authorization` | Thông tin chứng thực, ví dụ `Bearer` token. |
| `Cache-Control` | Chỉ dẫn hành vi cache. |
| `Location` | URI được thông báo, thường dùng khi tạo tài nguyên hoặc redirect. |
| `Set-Cookie` / `Cookie` | Server đặt cookie; client gửi cookie ở những request sau khi phù hợp. |

**`Accept` không đồng nghĩa `Content-Type`:** request có `Content-Type: application/json` nghĩa là body request là JSON; `Accept: application/json` nghĩa là client muốn response JSON. Cả hai có thể xuất hiện cùng lúc và mang vai trò khác nhau.

Header có thể tác động mạnh đến hành vi. Không ghi lộ giá trị `Authorization`, cookie phiên hay dữ liệu cá nhân vào log. Không ghép trực tiếp dữ liệu người dùng có chứa CR/LF vào header vì có thể tạo lỗ hổng HTTP response splitting.

### 3.4. Message body và cách xác định ranh giới

Body không phải lúc nào cũng có:
- `GET` thông thường chỉ lấy dữ liệu và không gửi body; không nên thiết kế API dựa vào body của GET vì ngữ nghĩa chung chưa được định nghĩa và các bên trung gian có thể không hỗ trợ.
- `POST` hoặc `PUT` thường gửi JSON/form/file trong body, nhưng method không tự buộc body phải có mặt.
- Response `204 No Content` và `304 Not Modified` không được chứa message content; response cho `HEAD` cũng không mang content body dù một số header mô tả response tương ứng của GET.
- Một lỗi mạng có thể khiến body nhận chưa đủ dù đã có status-line và headers.

**Phân định body HTTP/1.1** phải theo quy tắc framing của giao thức, không đoán bằng “đọc cho tới dòng trống thứ hai”. Tùy trường hợp, có `Content-Length`, `Transfer-Encoding: chunked`, hoặc cơ chế kết thúc kết nối; một số loại message không được phép có body. `chunked` là cơ chế mã hóa truyền trên HTTP/1.1, không phải một kiểu JSON hay một kiểu body ứng dụng. Không dùng đồng thời `Content-Length` và `Transfer-Encoding` để tự xây message: sự mơ hồ framing có nguy cơ gây request smuggling. Để HTTP library/server xử lý framing.

Với UTF-8, số byte có thể lớn hơn số ký tự: `"Lan"` trong JSON ASCII có số byte bằng số ký tự, nhưng `"Chào"` chứa ký tự đa byte. Nếu tự thao tác raw socket, độ dài phải tính trên byte đã mã hóa; trong Spring MVC bình thường, framework/web server xử lý phần này.

## 4. Ví dụ hoàn chỉnh: yêu cầu tạo tài nguyên

Đây là *trao đổi HTTP/1.1 minh họa*, giả định cả hai bên gửi đúng các header và body thể hiện bên dưới.

Request:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Content-Length: 14

{"name":"Lan"}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/42
Content-Type: application/json
Content-Length: 15

{"status":"ok"}
~~~

Diễn giải lần lượt:
1. `POST /api/orders` yêu cầu server xử lý dữ liệu và tạo một đơn hàng theo thiết kế API.
2. `Content-Type` nói với server cách parse body `{"name":"Lan"}`. Nội dung mẫu có 14 byte ASCII.
3. Server hoàn thành việc tạo tài nguyên và trả `201 Created`; đây là status phù hợp cho trường hợp tạo mới thành công.
4. `Location: /api/orders/42` cho client biết URI của tài nguyên vừa tạo (ở đây là URI tương đối).
5. Body response `{"status":"ok"}` dài 15 byte và có media type JSON.

Các chuỗi trên là **mẫu trao đổi cố định để đọc giao thức**, không khẳng định Spring tự tạo đúng JSON/URI/header này. Trong dự án thật, status, serialization, header và chính sách xử lý lỗi phụ thuộc controller, framework, cấu hình server và proxy.

## 5. Method, status code và ngữ nghĩa của phản hồi

Phân biệt **cú pháp message** với **ngữ nghĩa method/status**. Hai request có cấu trúc giống nhau nhưng method khác sẽ mang ý định khác.

| Method | Ý nghĩa thường gặp | Đặc điểm ngữ nghĩa |
| --- | --- | --- |
| `GET` | Lấy representation | Safe và idempotent theo định nghĩa HTTP; không nên gây thay đổi trạng thái do client yêu cầu. |
| `HEAD` | Lấy metadata tương ứng GET, không lấy body response | Safe, idempotent. |
| `POST` | Gửi dữ liệu để tài nguyên đích xử lý | Thông thường không idempotent. |
| `PUT` | Tạo/thay thế trạng thái tài nguyên tại URI đích theo representation gửi lên | Idempotent theo ngữ nghĩa chuẩn. |
| `PATCH` | Áp dụng thay đổi từng phần | Không mặc nhiên idempotent; phụ thuộc patch cụ thể. |
| `DELETE` | Yêu cầu xóa liên kết/trạng thái tài nguyên tại đích | Idempotent theo ngữ nghĩa HTTP, dù phản hồi những lần gọi có thể khác. |
| `OPTIONS` | Hỏi các tùy chọn giao tiếp | Safe, idempotent. |

**Safe** nói về ngữ nghĩa không yêu cầu thay đổi trạng thái có chủ đích (logging/metrics phụ trợ vẫn có thể xảy ra). **Idempotent** nghĩa là tác động *dự kiến trên server* của một hay nhiều request giống nhau là như nhau; không có nghĩa response byte-for-byte giống nhau hoặc mạng bảo đảm không gửi trùng.

Các nhóm status:
- **1xx – Informational:** phản hồi trung gian, ví dụ `100 Continue`.
- **2xx – Success:** `200 OK` có nội dung thành công tùy method; `201 Created` khi tạo; `204 No Content` khi thành công và không có content.
- **3xx – Redirection:** client cần dùng thông tin điều hướng/cache, ví dụ `301`, `302`, `304`; 304 phục vụ tái sử dụng representation đã cache, không phải body mới.
- **4xx – Client error:** `400 Bad Request` cho request không hợp lệ; `401 Unauthorized` liên quan yêu cầu xác thực; `403 Forbidden` bị từ chối truy cập; `404 Not Found` không tìm thấy representation/tài nguyên theo ngữ cảnh.
- **5xx – Server error:** `500 Internal Server Error` cho lỗi xử lý phía server; `502 Bad Gateway` thường liên quan gateway/proxy nhận upstream không hợp lệ; `503 Service Unavailable` báo tạm không sẵn sàng.

Một status 2xx chỉ xác nhận cách xử lý **theo giao thức và hợp đồng API**. Ví dụ endpoint có thể trả 200 nhưng JSON `{"success":false}`; đó là quyết định thiết kế ứng dụng, không khiến 200 tự động có nghĩa “mọi nghiệp vụ đã thành công”. Hãy xem đồng thời HTTP status và schema phản hồi của API.

## 6. HTTP đi vào Spring Web như thế nào?

Ví dụ bên dưới là **một controller Spring MVC minh họa**, sử dụng Java 17+, Spring Framework 6/Spring Boot 3, module `spring-webmvc` và JSON converter như Jackson. Đặt vào tệp `GreetingController.java` bên trong source set của ứng dụng Spring có cấu hình tự động quét component. Đoạn này *không phải chương trình Java độc lập để chạy bằng lệnh `javac` thuần*, vì cần dependency và ứng dụng web đang hoạt động.

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    @GetMapping("/{name}")
    public ResponseEntity<GreetingResponse> greet(@PathVariable String name) {
        return ResponseEntity.ok(new GreetingResponse("Xin chào, " + name + "!"));
    }

    public record GreetingResponse(String message) {}
}
~~~

Khi ứng dụng Spring MVC chạy trên cổng 8080, thử:

~~~bash
curl --http1.1 -i -H "Accept: application/json" http://localhost:8080/api/greetings/Lan
~~~

Trong PowerShell, nếu `curl` là alias của `Invoke-WebRequest`, hãy gọi `curl.exe` để dùng cú pháp curl CLI.

Ví dụ phần body JSON kỳ vọng (format header và cách hiện ký tự Unicode có thể khác theo môi trường):

~~~json
{"message":"Xin chào, Lan!"}
~~~

Giải thích đường đi trong Spring MVC:

1. Client gửi `GET /api/greetings/Lan`. Servlet container nhận request HTTP và tạo thông tin request/response cho tầng servlet.
2. Các `Filter` được cấu hình có thể kiểm tra request hoặc response (ví dụ logging, bảo mật), rồi luồng xử lý đi đến `DispatcherServlet`.
3. `DispatcherServlet` nhờ `HandlerMapping` tìm handler phù hợp với `GET` và path; `HandlerAdapter` thực thi phương thức controller.
4. `@PathVariable` ràng buộc đoạn `Lan` của path vào biến Java `name`. `ResponseEntity.ok(...)` đặt HTTP status là 200.
5. Vì controller là `@RestController`, giá trị `GreetingResponse` được xử lý như response body; `HttpMessageConverter` phù hợp (thường là Jackson JSON converter) serialize record thành JSON.
6. Servlet container gửi status, headers và body tới client. Spring/server có thể bổ sung header khác, dùng chunked transfer hoặc một cơ chế framing hợp lệ; không tự suy luận `Content-Length` nếu response thực tế không có.

Ở chiều **request body**, một API kiểu `@PostMapping` với `@RequestBody` thường dùng converter để deserialize JSON request vào đối tượng Java. Nếu media type không được hỗ trợ, request sai cấu trúc hoặc validation thất bại, Spring có thể trả lỗi 4xx theo cấu hình xử lý lỗi. Một JSON body hợp lệ không đảm bảo nghiệp vụ hợp lệ.

Đây là pipeline **Spring MVC (Servlet)**. Với Spring WebFlux, lớp điều phối và mô hình xử lý là reactive (ví dụ `DispatcherHandler`); không nên áp nguyên sơ đồ `DispatcherServlet` cho WebFlux.

## 7. Tự quan sát request và response khi gỡ lỗi

Dùng `curl -i` để xem **status-line và response headers cùng body** ở đầu ra. Thêm `-v` để xem thêm thông tin kết nối và request/response từ phía client; `--http1.1` ép HTTP/1.1 cho thí nghiệm về cú pháp. Trong DevTools của trình duyệt, tab Network giúp xem URL, method, status, headers, payload, timing; công cụ có thể hiển thị dữ liệu theo giao diện đã giải mã chứ không phải raw bytes thực sự truyền trên mạng.

Thứ tự kiểm tra khi lỗi:
1. **Không có status code?** Kiểm tra DNS, kết nối, TLS, timeout, proxy và server availability trước khi đổ lỗi cho controller.
2. **Có 4xx?** Kiểm tra method, path/query, `Content-Type`, `Accept`, xác thực, phân quyền, JSON body, giới hạn kích thước và hợp đồng API.
3. **Có 5xx?** Đối chiếu log/tracing phía server và upstream; tránh tiết lộ stack trace hay credential ra response công khai.
4. **Status đúng nhưng client parse lỗi?** Kiểm tra `Content-Type`, charset/encoding, body rỗng (đặc biệt 204/HEAD), dạng JSON và dữ liệu thực nhận.
5. **Chỉ hỏng qua proxy?** Kiểm tra rewrite path/host, forwarding headers, kích thước header/body, timeout và sự nhất quán HTTP framing.

HTTP status thuộc response thực tế của một request. **Timeout không phải HTTP 408 tự động**: 408 là một status server có thể trả trong điều kiện nhất định; nếu mất kết nối hoặc hết thời gian ở client mà không có response thì client chỉ thấy lỗi truyền thông.

## 8. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| “HTTP chỉ là JSON API.” | HTTP mang nhiều media type; body có thể vắng mặt hoặc là dữ liệu nhị phân. |
| “Request nào cũng có body.” | Không; sự hiện diện và ngữ nghĩa body phụ thuộc loại message và method/status. |
| “Query string chính là body.” | Query thuộc request-target/URI; body nằm sau headers. |
| “Content-Length đếm ký tự.” | Đếm byte; UTF-8 có ký tự nhiều byte. |
| “Có HTTPS nghĩa là method/header/body khác đi.” | HTTPS bảo vệ HTTP khi truyền; ngữ nghĩa HTTP vẫn tương ứng, dù tầng transport/phiên bản có thể khác. |
| “HTTP/2 trên dây cũng có status-line 200 OK.” | HTTP/2 dùng frames và `:status`; start-line là cú pháp HTTP/1.x. |
| “200 luôn nghĩa là nghiệp vụ hoàn tất.” | Cần hiểu cả hợp đồng API và body của phản hồi. |
| “PUT/DELETE idempotent nghĩa là không có tác dụng phụ.” | Idempotent nói về hiệu ứng dự kiến khi lặp lại; logging, audit hoặc response vẫn có thể thay đổi. |
| “Backend luôn nhận đúng request-line client gửi.” | Proxy có thể chỉnh path, host, forwarding headers và phiên bản giao thức. |

## 9. Tự kiểm tra kiến thức

**Bài 1.** Xét request: `GET /products?sort=price HTTP/1.1`, có `Host: shop.example.test` và `Accept: application/json`. Hãy xác định method, path, query, hai header và body có bắt buộc không.

**Bài 2.** Client gửi JSON UTF-8 có dấu tiếng Việt nhưng tự lấy `String.length()` làm `Content-Length`. Rủi ro là gì?

**Bài 3.** Server trả `HTTP/1.1 204 No Content`. Client có nên cố parse JSON từ body không?

**Bài 4.** Controller `@GetMapping("/api/greetings/{name}")` trả `ResponseEntity.ok(...)`. Những phần nào quyết định path mapping, status và JSON serialization?

**Đáp án và giải thích**

1. Method là `GET`; path là `/products`; query là `sort=price`; headers là `Host` và `Accept`; GET không bắt buộc có body và API không nên phụ thuộc GET body.
2. `String.length()` trong Java đếm UTF-16 code units; `Content-Length` đếm bytes trong nội dung HTTP/1.1. Với UTF-8, số này có thể lệch, làm sai framing và dẫn đến lỗi truyền thông/bảo mật; để HTTP library tính theo bytes.
3. Không. Response 204 không có content; client cần xử lý body rỗng theo status.
4. `@GetMapping`/`HandlerMapping` quyết định route và method; `ResponseEntity.ok` đặt status 200; `@RestController` cùng `HttpMessageConverter` thích hợp quyết định serialize response body sang JSON.

## 10. Ghi nhớ khi xây API Spring Web

Đầu tiên xác định **resource và hành vi HTTP** (URI/method/status). Sau đó đặt đúng dữ liệu vào **path, query, headers hay body**, công bố định dạng qua `Content-Type` và xử lý thương lượng nội dung khi cần. Khi trả response, đảm bảo status phản ánh kết quả xử lý, body tuân theo status, và giao thức/header framing được thư viện HTTP đảm nhiệm. Nhờ mô hình này, bạn có thể giải thích một request và response cả ở mức raw HTTP/1.1 lẫn ở controller Spring MVC mà không nhầm lẫn vai trò của từng tầng.

**Tài liệu chuẩn để đối chiếu sâu:** RFC 9110 (HTTP Semantics), RFC 9112 (HTTP/1.1 message syntax và framing), RFC 9113 (HTTP/2) và RFC 9114 (HTTP/3).