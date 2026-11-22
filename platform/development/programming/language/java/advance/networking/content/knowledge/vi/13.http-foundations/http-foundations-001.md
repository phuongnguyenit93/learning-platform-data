# HTTP bổ sung mô hình yêu cầu–phản hồi lên cơ chế vận chuyển

HTTP (Hypertext Transfer Protocol) là **giao thức tầng ứng dụng** cung cấp **ngữ nghĩa yêu cầu–phản hồi (request–response)** để client tương tác với tài nguyên do server cung cấp. Cơ chế vận chuyển (transport) lo việc mang dữ liệu giữa những endpoint; HTTP bổ sung câu trả lời cho các câu hỏi mà transport **không tự định nghĩa**: *đây là yêu cầu làm gì, nhằm vào tài nguyên nào, body có kiểu gì, server đã xử lý ra sao, có thể cache hay thử lại không?*

Một TCP socket cung cấp dòng byte tin cậy, có thứ tự trong một kết nối; nó **không biết** `GET`, `POST`, đường dẫn `/products/42`, header `Content-Type` hay mã `404` là gì. HTTP quy định **cấu trúc thông điệp và ý nghĩa** của những phần đó. Khi dùng HTTP/1.1, các thông điệp được biểu diễn dạng dòng mở đầu, header và body trên một kết nối byte stream. HTTP/2 dùng các frame nhị phân và stream logic trên TCP; HTTP/3 mang ngữ nghĩa HTTP qua **QUIC** (dựa trên UDP nhưng cung cấp truyền dữ liệu đáng tin cậy theo stream và bảo mật tích hợp).

**Điều cần ghi nhớ:** *HTTP không thay thế transport; nó dùng khả năng của transport/phiên kết nối để chuyển tải thông điệp có ngữ nghĩa ứng dụng.* Ngược lại, chỉ có transport hoạt động tốt **chưa đủ** để biết một request hợp lệ, được phép hay được thực thi thành công.

Bài này thuộc chủ đề **Nền tảng HTTP** của module **Java Advance - networking**. Trọng tâm là mô hình request–response, phân tầng, format và semantics giữa các phiên bản HTTP, ví dụ thực hành Java 17+ và các lỗi nền tảng cần tránh.

## 1. Mục tiêu học tập

Sau bài học, bạn sẽ có khả năng:

1. Phân biệt **byte stream/transport** với **HTTP request, response, headers, body và semantics**.
2. Diễn giải một vòng từ client tạo request → transport chuyển dữ liệu → server nhận/parse/xử lý → tạo response → client kiểm tra status và body.
3. Đọc thông điệp HTTP/1.1: request line, header fields, dòng trống phân cách, body, status line; nêu ý nghĩa `Host`, `Content-Length` và `Connection`.
4. Giải thích method, target resource, status codes, representation, media type, cache metadata và các thuộc tính **safe/idempotent**.
5. Phân biệt HTTP **stateless** với việc TCP/TLS connection **persistent**, cookie/session và authentication.
6. Hiểu vì sao HTTP/1.1, HTTP/2 và HTTP/3 **giữ cùng ngữ nghĩa ứng dụng** nhưng khác cách framing và transport.
7. Giải thích HTTPS/TLS, proxy, reverse proxy, gateway và các lỗi xảy ra ở mỗi tầng.
8. Viết một HTTP client/server nhỏ bằng Java 17; thử gửi HTTP/1.1 trực tiếp qua `Socket` để thấy phần nào do application implement.
9. Áp dụng timeout, body length/framing, giới hạn tài nguyên, retry/caching và xử lý lỗi đúng cấp.

## 2. Sơ đồ các tầng: transport có gì và HTTP thêm gì?

~~~text
ỨNG DỤNG CLIENT                    ỨNG DỤNG SERVER
"Đọc tài nguyên /demo"             "Xử lý /demo"
       |                                   ^
       v                                   |
+-------------------+            +----------------------+
| HTTP semantics    |            | HTTP semantics       |
| GET /demo         |            | route, method, status|
| Host, Accept      |            | headers, response    |
+---------+---------+            +----------+-----------+
          |                                   ^
          v                                   |
+-------------------+            +----------------------+
| HTTP message      |            | HTTP parser/framer    |
| encoding/framing  |            | and response encoder  |
| HTTP/1.1, h2, h3  |            +----------+-----------+
+---------+---------+                       ^
          |                                 |
          v                                 |
+-------------------+            +----------------------+
| Transport/session | ---------->| Transport/session    |
| TCP, TLS/TCP      |   network  | TCP, TLS/TCP         |
| or QUIC over UDP  |            | or QUIC over UDP     |
+-------------------+            +----------------------+
~~~

**Phân biệt trách nhiệm:**

| Lớp/khái niệm | Giải quyết | Không tự giải quyết |
| --- | --- | --- |
| IP/routing | Chuyển packet giữa mạng và endpoint | Không hiểu HTTP method/status |
| TCP | Connection, byte stream có thứ tự, retransmission, flow/congestion control | Không xác định ranh giới một HTTP message hoặc semantics nghiệp vụ |
| TLS (thường đi với HTTPS trên TCP) | Bảo vệ bí mật/toàn vẹn, xác thực server bằng certificate và các khả năng TLS khác | Không tự hiểu request `GET`/`POST` hay đáp ứng authorization ứng dụng |
| QUIC | Transport hiện đại trên UDP: multiplexed streams, reliability từng stream, connection security | Không quyết định ý nghĩa URI/method/status |
| HTTP semantics | Resource, method, status, headers, representation, caching và hành vi trung gian | Không tự bảo đảm một network route thông suốt hay một giao dịch business được commit |
| Ứng dụng | Kiểm tra quyền, dữ liệu, transaction, domain rules, idempotency key khi cần | Không nên tự coi TCP ACK là xác nhận nghiệp vụ |

Ví dụ: client gọi `Socket.write("GET /x ...")` gửi byte vào TCP. Nếu bên kia không có **HTTP parser**, chuỗi này chỉ là dữ liệu ASCII; server có thể hiểu là lệnh của một giao thức tùy ý hoặc không hiểu gì. Ngược lại, hai chương trình dùng thư viện HTTP thích hợp có thể giao tiếp mà ứng dụng không cần tự đếm byte CRLF hay phân tích TCP segments.

### Giao tiếp HTTP không phải phép cộng 1 request = 1 TCP packet

- TCP có thể **chia** một HTTP request thành nhiều đoạn hoặc **gộp** nhiều thao tác ghi vào các đoạn mạng.
- Một lần `InputStream.read()` có thể nhận một phần header, một phần body hoặc nhiều byte hơn mong đợi của một message.
- Một TCP connection có thể chuyên chở **nhiều HTTP request–response exchanges** theo version và phương thức sử dụng connection.
- HTTP/2 và HTTP/3 có **nhiều streams logic** đồng thời trên cùng một transport connection. Không được coi số socket luôn bằng số HTTP requests.

**Bất biến:** ứng dụng phải xác định **ranh giới message** theo HTTP version/framing, không theo số lần `read()` hoặc số network packets.

## 3. Mô hình request–response hoạt động ra sao?

Một lượt trao đổi cơ bản:

~~~text
Client                                                Server
  |                                                     |
  | (1) GET /items/42 HTTP/1.1                          |
  |     Host: shop.example                              |
  |     Accept: application/json                         |
  |---------------------------------------------------->|
  |                    (2) nhận và parse message         |
  |                    (3) route, auth, đọc resource      |
  |                                                     |
  | (4) HTTP/1.1 200 OK                                |
  |     Content-Type: application/json                   |
  |     Content-Length: ...                              |
  |     {"id":42,"name":"Pen"}                           |
  |<----------------------------------------------------|
  |                                                     |
  | (5) client kiểm tra status, headers, body            |
  |                                                     |
~~~

`shop.example` và `/items/42` chỉ là ví dụ minh họa, không phải endpoint thực tế được thử nghiệm.

**Request** mô tả *điều client muốn server thực hiện*, gồm:

- **Method**: `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, v.v.
- **Target URI/resource**: tài nguyên muốn truy cập, ví dụ `https://shop.example/items/42`.
- **Header fields**: metadata và control information như `Host`, `Accept`, `Content-Type`, `Authorization`, `If-None-Match`.
- **Content/body**: có thể có hoặc không; ý nghĩa phụ thuộc method và media type/giao thức ứng dụng.

**Response** mô tả *kết quả server xử lý request*, gồm:

- **Status code**: như `200` thành công, `201` tạo mới, `404` resource không tồn tại/không tìm thấy, `500` lỗi server.
- **Response header fields**: `Content-Type`, `Cache-Control`, `ETag`, `Location` và các metadata khác.
- **Response content**: HTML, JSON, hình ảnh, file hoặc nội dung khác; một số response không có body theo semantics.

Một request có thể nhận **response tạm thời 1xx** (như `100 Continue`) trước khi có response cuối cùng. Vì vậy mô hình “một request → một response” là mô hình **request–response transaction**; ở wire level có thể có thông báo tạm thời đi trước final response.

**Không đồng nhất response với kết quả domain:** HTTP 200 có nghĩa server đã trả một response biểu thị thành công của request ở mức HTTP, nhưng không chứng minh mọi sự kiện downstream sau đó hoàn tất (ví dụ gửi email bất đồng bộ). HTTP 202 Accepted có thể biểu thị request được chấp nhận để xử lý tiếp, không có nghĩa công việc đã hoàn thành.

## 4. HTTP/1.1 trên TCP: cấu trúc thông điệp hiển thị được

Khi kết nối TCP thuần `http://` đến server HTTP/1.1, phần đầu thông điệp thường đọc được bằng text. Một request đơn giản:

~~~http
GET /hello?lang=vi HTTP/1.1
Host: example.test
Accept: text/plain
Connection: close

~~~

Đây là **biểu diễn bằng dòng**. Trong thực tế, mỗi dòng header/request line kết thúc bằng **CRLF** (ký tự `\r\n`) và sau header cuối là **dòng trống CRLF**. Không tự nghĩ newline trên terminal mọi OS đều tương đương CRLF của HTTP/1.1.

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Length: 5
Connection: close

Hello
~~~

`Content-Length: 5` vì chuỗi ASCII `Hello` dài 5 **byte**. Với tiếng Việt có dấu, độ dài UTF-8 theo byte có thể **khác** số ký tự Java `String.length()`. Nếu server tự viết HTTP/1.1 thì cần tính chính xác **số byte được gửi**, không phải số code points hoặc số ký tự màn hình.

### 4.1. Request line và resource target

Trong HTTP/1.1, request line thường có dạng:

~~~text
METHOD SP request-target SP HTTP-version CRLF

GET /hello?lang=vi HTTP/1.1
~~~

- `GET` là method định nghĩa semantics của hành động.
- `/hello?lang=vi` là request target ở dạng **origin-form** phổ biến khi client gửi trực tiếp đến origin server.
- `HTTP/1.1` mô tả version được dùng cho biểu diễn trao đổi này.
- `Host` ở HTTP/1.1 là header bắt buộc với các request thông thường, giúp server nhận diện authority/virtual host. Không tự chọn target resource chỉ từ TCP local port.

URI đầy đủ `https://example.test/hello?lang=vi` chứa scheme, authority, path và query; fragment `#section` nếu có được client xử lý cục bộ và **không** gửi như thành phần của request-target HTTP thông thường.

Ở HTTP/2 và HTTP/3 không có request line dạng text này trên wire; semantics tương đương được mã hóa trong pseudo-header fields như `:method`, `:scheme`, `:authority`, `:path` (tùy trường hợp).

### 4.2. Status line và status code

Trong HTTP/1.1, một response bắt đầu bằng:

~~~text
HTTP/1.1 SP status-code SP reason-phrase CRLF

HTTP/1.1 404 Not Found
~~~

Reason phrase là văn bản giải thích mang tính tùy chọn/chủ yếu để người đọc hiểu trong HTTP/1.1; logic client nên dựa vào **status code** thay vì so khớp tuyệt đối `"Not Found"`. HTTP/2 và HTTP/3 truyền mã status qua `:status` thay vì status line dạng text.

### 4.3. Header, blank line và body

Header fields mô tả thêm yêu cầu/response, ví dụ:

~~~http
POST /messages HTTP/1.1
Host: example.test
Content-Type: application/json
Content-Length: 16

{"text":"hello"}
~~~

Ở ví dụ này `{"text":"hello"}` dài 16 byte ASCII, nên `Content-Length` = 16. Header **không** phải body; `Content-Type` mô tả media type của **nội dung biểu diễn**. `Accept` bên request mô tả các dạng response client mong muốn; không đồng nghĩa `Content-Type` của body client gửi.

Các tên HTTP header **không phân biệt chữ hoa/thường** trong semantics; nhưng không được tự ý thay đổi nội dung/format header tùy tiện khi viết parser. Dùng thư viện HTTP thay vì tự phân tích trong production để tránh lỗi cú pháp và bảo mật.

### 4.4. Message framing: body kết thúc ở đâu?

TCP chỉ thấy byte stream, không thấy ranh giới HTTP message. Trong HTTP/1.1, server/client phải áp dụng **quy tắc xác định độ dài thông điệp** theo HTTP; những cách thường thấy gồm:

- **`Content-Length`**: xác định độ dài **byte** của content khi phù hợp với quy tắc HTTP.
- **`Transfer-Encoding: chunked`**: chia content thành các chunk có kích thước biểu diễn theo hex, kết thúc bằng zero-size chunk (và có thể có trailer fields). Đây là cơ chế message framing của HTTP/1.1, không phải encoding JSON hay một dạng nén.
- **Đọc đến khi connection đóng**: chỉ dùng trong những trường hợp response được định nghĩa là close-delimited; không an toàn để coi đây là quy tắc chung, vì persistent connections có thể vẫn mở sau response.
- **Các response không có body theo semantics**, ví dụ response cho `HEAD`, `204 No Content` và `304 Not Modified`, có quy tắc riêng; không tự đọc body chỉ vì nhìn thấy một header lạ.

Thứ tự ưu tiên và các trường hợp bất hợp lệ phải được xử lý đúng như RFC 9112; nếu `Transfer-Encoding` và `Content-Length` xung đột, proxy/parser khác nhau có thể dẫn đến request smuggling. Không viết parser HTTP/1.1 thủ công cho sản phẩm thật chỉ dựa vào vài dòng ví dụ trong bài.

**Sai lầm điển hình:** server gửi body gồm 12 byte nhưng khai báo `Content-Length: 20`; client có thể chờ 8 byte nữa hoặc cho rằng response chưa đầy đủ. Ngược lại, khai báo quá ngắn khiến phần còn dư bị hiểu sai, đặc biệt khi connection tái sử dụng.

## 5. HTTP bổ sung những semantics gì lên trên transport?

Transport có thể đưa dữ liệu từ A tới B, nhưng HTTP bổ sung một **giao diện thống nhất** cho tài nguyên (`resource`), method, metadata, status và caching.

### 5.1. Resource, representation và URI

Một HTTP resource không phải “file nằm ở path giống hệt URL”. Nó là thực thể khái niệm được **định danh bởi URI** và được origin server ánh xạ sang hành vi hoặc các biểu diễn (`representation`).

Ví dụ:

- `GET /users/7` có thể trả JSON chứa thông tin user.
- `GET /reports/monthly` có thể sinh PDF động, không phải đọc một file cố định.
- `GET /images/logo` có thể trả PNG/WebP tùy `Accept`, hoặc một lỗi nếu không được phép.
- `POST /jobs` có thể tạo job bất đồng bộ và trả `202 Accepted`.

**URI** định danh hoặc xác định đích; **representation** là dữ liệu cụ thể mà HTTP truyền cùng metadata tương ứng. Đừng đồng nhất URI với đường dẫn filesystem, hoặc JSON với bản thân resource.

### 5.2. Method là hợp đồng ý nghĩa, không phải lệnh TCP

| Method | Ý nghĩa tiêu biểu | Safe? | Idempotent? |
| --- | --- | --- | --- |
| `GET` | Lấy representation hiện tại của resource | Có | Có |
| `HEAD` | Như GET về metadata nhưng response không có body | Có | Có |
| `POST` | Yêu cầu resource đích xử lý nội dung theo semantics cụ thể | Không mặc định | Không mặc định |
| `PUT` | Tạo/thay thế trạng thái resource đích theo representation gửi | Không | Có |
| `DELETE` | Yêu cầu xóa liên kết/chức năng của resource đích | Không | Có |
| `PATCH` | Áp dụng thay đổi một phần cho resource | Không | Không mặc định |
| `OPTIONS` | Hỏi khả năng giao tiếp/tuỳ chọn | Có | Có |
| `TRACE` | Kiểm tra request loopback theo quy định HTTP (thường bị tắt vì an ninh) | Có theo semantics | Có |

**Safe** nghĩa là client không *yêu cầu* thay đổi trạng thái tài nguyên; server vẫn có thể ghi log, thống kê hoặc hiệu ứng phụ ngoài ý muốn. GET nên được thiết kế không gây thay đổi nghiệp vụ dù người dùng có refresh hay crawler truy cập.

**Idempotent** nghĩa là nhiều request giống hệt có **cùng hiệu ứng dự kiến lên trạng thái** như thực hiện một lần, không có nghĩa response từng lần luôn giống nhau. Ví dụ DELETE resource lần đầu có thể trả 204, lần sau 404; điều đó không phủ nhận semantics idempotent của DELETE.

PUT và DELETE được định nghĩa idempotent ở mức HTTP semantics, nhưng triển khai application có side effect (phí tiền mỗi lần, gửi mail mỗi lần) có thể phá thuộc tính đó; API phải thực thi đúng hợp đồng. POST tạo mới thường cần `Idempotency-Key` hoặc cơ chế deduplication riêng nếu client có thể retry mà không muốn tạo trùng giao dịch.

**Không dựa vào tên method để bỏ qua authorization.** Một request GET không có nghĩa “mọi người đều được đọc dữ liệu”; một request POST không có nghĩa “server chắc chắn đã ghi database”.

### 5.3. Status codes: outcome ở tầng HTTP

| Nhóm | Ý nghĩa cơ bản | Ví dụ quan trọng |
| --- | --- | --- |
| `1xx` | Informational, trước final response | `100 Continue`, `101 Switching Protocols` |
| `2xx` | Request đã được nhận/hiểu/chấp thuận theo semantics thành công | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Redirect hoặc cần client hành động với representation/URI | `301`, `302`, `304 Not Modified`, `307`, `308` |
| `4xx` | Client request có vấn đề hoặc không được phép/thể hiện lỗi liên quan request | `400`, `401`, `403`, `404`, `405`, `408`, `409`, `429` |
| `5xx` | Server không thể thực hiện request hợp lệ hoặc có lỗi server/downstream | `500`, `502`, `503`, `504` |

Một vài phân biệt dễ nhầm:

- `401 Unauthorized` thường biểu thị **chưa có thông tin xác thực hợp lệ** (đòi cơ chế authentication), còn `403 Forbidden` là server từ chối quyền, dù đã nhận diện chủ thể.
- `404 Not Found` nói resource không tìm thấy hoặc server không muốn tiết lộ sự tồn tại; không chứng minh DNS/TCP thất bại.
- `429 Too Many Requests` thường dùng rate limiting; có thể kết hợp `Retry-After` theo policy.
- `502 Bad Gateway` / `504 Gateway Timeout` thường xuất phát từ gateway/proxy liên quan upstream; khác lỗi transport client chưa mở được connection tới proxy.
- `304 Not Modified` là kết quả của conditional request dùng cache, **không phải response body mới**.
- `204 No Content` là thành công nhưng không có content trong response.
- `201 Created` thường dùng sau tạo resource và có thể có header `Location`.
- `202 Accepted` không tự đảm bảo việc xử lý bất đồng bộ cuối cùng sẽ thành công.

Đây là **mã ý nghĩa HTTP**, không phải mã lỗi TCP của `Socket.connect()`. Khi client nhận HTTP 500, ít nhất một server/gateway HTTP đã trả lời; khi DNS lookup thất bại, thường **chưa có HTTP response** để đọc.

### 5.4. Header mô tả representation, điều kiện và cache

Một số header đáng học ở nền tảng:

| Header | Thường ở đâu | Vai trò |
| --- | --- | --- |
| `Host` | Request HTTP/1.1 | Authority/virtual host |
| `Accept` | Request | Media types client có thể chấp nhận cho response |
| `Content-Type` | Request/response có content | Kiểu media/charset của representation |
| `Content-Length` | Message cần length framing | Số byte content theo quy tắc version |
| `Authorization` | Request | Thông tin xác thực để server kiểm tra |
| `Cookie` / `Set-Cookie` | Request / response | Mang/truyền state của application layer khi dùng cookies |
| `Cache-Control` | Request/response | Chỉ thị cache, freshness và policy |
| `ETag` | Response | Validator của representation |
| `If-None-Match` | Request | Conditional request dựa trên ETag |
| `Location` | Response phù hợp | Đích redirect/resource mới |
| `Accept-Encoding` / `Content-Encoding` | Request / response | Thương lượng và thông báo content coding |
| `Connection` | HTTP/1.1 | Connection-control metadata cho hop hiện tại, **không dùng như vậy ở HTTP/2/3** |
| `Via` | Request/response qua intermediary | Ghi nhận bước proxy/gateway theo tiêu chuẩn |

Header là **metadata**, không phải giấy phép để server tin mọi giá trị do client gửi. `Authorization` cần được validate, `Content-Length` phải parse chính xác, `Host` cần chống host-header attacks khi tạo link/redirect. Các header hop-by-hop có quy tắc khác với end-to-end fields; proxy phải thực hiện đúng khi chuyển tiếp.

## 6. HTTP stateless nhưng vẫn có session và connection reuse

HTTP được định nghĩa là một **giao thức stateless về semantics**: ý nghĩa mỗi request có thể hiểu độc lập, không bắt buộc phải giữ lịch sử request trước trên transport connection.

**Stateless không có nghĩa:**

- Server không được lưu database hoặc trạng thái ứng dụng.
- Một client không thể đăng nhập.
- Cookie/authorization token không tồn tại.
- Mỗi HTTP request buộc phải mở TCP connection mới.
- HTTP server không thể xử lý nhiều request của cùng user theo một workflow.

Ví dụ app giữ session bằng cookie:

~~~http
GET /account HTTP/1.1
Host: example.test
Cookie: session=opaque-token

~~~

Server đọc cookie, xác thực token/session và trả tài khoản tương ứng. **State** nằm trong cookie/token/server-side session store hoặc hạ tầng, không phải do TCP tự nhớ “client vừa đăng nhập”. Nếu client mở một connection mới nhưng gửi credential hợp lệ, API có thể tiếp tục làm việc.

Cần phân biệt:

- **HTTP request state**: method, URI, headers/body của lượt trao đổi.
- **Application session state**: cookie, token, database record, giao dịch nghiệp vụ.
- **Transport connection state**: TCP/TLS/QUIC connection, cửa sổ flow control, retransmission và peer endpoint.

Đây là ba vòng đời khác nhau. Một connection có thể mang nhiều request, nhiều connection có thể phục vụ cùng một session, và một HTTP request có thể kết thúc mà background job của server vẫn tiếp tục.

## 7. Persistent connections, reuse và multiplexing

### 7.1. HTTP/1.1: keep-alive mặc định

HTTP/1.1 thường giữ connection mở để gửi nhiều request–response exchanges, giảm chi phí TCP/TLS handshake. Header `Connection: close` cho biết phía gửi định kết thúc connection sau khi hoàn tất response phù hợp; nó **không phải** dấu kết thúc một message duy nhất ở mọi trường hợp.

~~~text
TCP connection 1 (HTTP/1.1 persistent):
  Client -> request A
  Server -> response A
  Client -> request B
  Server -> response B
  ... (khi còn được phép và connection sống)

Nhiều requests không đòi hỏi nhiều TCP connections.
~~~

HTTP/1.1 còn có pipelining về mặt giao thức, nhưng ứng dụng/browser hiện đại thường không dựa vào nó do phức tạp, response ordering và head-of-line blocking. Đừng gán “một request một socket” cho mọi HTTP/1.1, càng không đúng ở HTTP/2/3.

Khi connection đang persistent, cách đọc `InputStream.readAllBytes()` “đến EOF” để lấy response là **sai** nếu server vẫn giữ connection mở. Parser phải đọc đến **đúng message boundary** theo HTTP framing.

### 7.2. HTTP/2: streams logic trên một TCP connection

HTTP/2 giữ semantics như GET/POST, target, headers và status nhưng thay format HTTP/1.1 bằng:

- **Binary frames**: ví dụ `HEADERS`, `DATA`, `SETTINGS` và `WINDOW_UPDATE`.
- **Streams**: nhiều request–response exchanges được multiplex qua một TCP connection.
- **Header compression HPACK** và quản lý flow control ở cấp stream/connection.
- **Pseudo-headers** như `:method`, `:scheme`, `:authority`, `:path` và `:status`.
- **Không còn** start line và chunked transfer coding giống HTTP/1.1 trên wire.

~~~text
TCP connection
  |
  +-- HTTP/2 Stream 1: GET /a -> 200, DATA...
  +-- HTTP/2 Stream 3: GET /b -> 200, DATA...
  +-- HTTP/2 Stream 5: POST /c -> 201, DATA...
  |
  Frames từ nhiều streams xen kẽ trên cùng TCP connection.
~~~

**Giới hạn quan trọng:** TCP vẫn là một byte stream có thứ tự ở dưới. Mất một TCP segment có thể làm dữ liệu của nhiều HTTP/2 streams bị chờ retransmission (*transport-level head-of-line blocking*), dù HTTP/2 cho phép interleave application frames.

### 7.3. HTTP/3: HTTP semantics qua QUIC (UDP không đồng nghĩa unreliable)

HTTP/3 theo RFC 9114 dùng **QUIC**, trong đó QUIC chạy trên **UDP** nhưng tự cung cấp cơ chế cần thiết để truyền byte **đáng tin cậy và có thứ tự trên từng stream**, cùng encryption/authentication, congestion control, stream multiplexing và flow control.

~~~text
HTTP semantics: GET, POST, 200, Content-Type, Cache-Control
                    |
              HTTP/3 frames
                    |
            QUIC streams + TLS 1.3
                    |
                     UDP
                    |
                     IP
~~~

So với HTTP/2:

- HTTP/3 multiplexing xảy ra nhờ **QUIC streams**, không phải nhét tất cả HTTP/2 streams vào một TCP byte stream.
- Mất packet QUIC liên quan stream A không phải buộc dữ liệu đã có của stream B chờ khôi phục byte của A theo thứ tự **trên một TCP stream chung**. QUIC vẫn có congestion control và giới hạn tài nguyên chung; không phải hoàn toàn độc lập về hiệu năng.
- HTTP/3 dùng **QPACK** cho header compression (thay vì HPACK của HTTP/2).
- Bảo mật được tích hợp qua QUIC/TLS 1.3; không xem HTTP/3 là “HTTP text gửi UDP không mã hóa”.
- Semantics method/status/URI/caching vẫn dựa trên HTTP chung, nhưng wire framing khác biệt.

**Không** dùng `DatagramSocket.send("GET / HTTP/1.1")` rồi cho rằng vừa tạo HTTP/3 request. HTTP/3 đòi hỏi **QUIC implementation**, handshake, streams và HTTP/3 framing đúng chuẩn.

## 8. Bảng so sánh ba phiên bản HTTP

| Khía cạnh | HTTP/1.1 | HTTP/2 | HTTP/3 |
| --- | --- | --- | --- |
| Semantics request–response | Có | Giữ semantics HTTP | Giữ semantics HTTP |
| Transport phổ biến | TCP (thường TLS cho HTTPS) | TCP + TLS trong triển khai web phổ biến | QUIC trên UDP, bảo mật tích hợp |
| Format | Dòng mở đầu + headers dạng text + body | Binary frames | HTTP/3 frames trên QUIC streams |
| Message demarcation | HTTP/1.1 framing (length/chunked/semantics) | Frame và stream state | QUIC stream + HTTP/3 frames |
| Multiplex nhiều request | Không có multiplex layer tương đương h2 | Có trên một TCP connection | Có nhờ QUIC streams |
| Header compression | Không chuẩn HPACK/QPACK | HPACK | QPACK |
| Head-of-line blocking | Có ở tầng HTTP/1.1 connection theo cách dùng | TCP-level có thể chặn các h2 streams | Không có cùng kiểu TCP-level HoL giữa QUIC streams |
| Nguyên tắc status/method | `GET`/`200`/... | Như HTTP semantics | Như HTTP semantics |
| Java 17 `java.net.http.HttpClient` | Hỗ trợ | Hỗ trợ HTTP/2 theo API và negotiation | **Không hỗ trợ HTTP/3 theo API chuẩn Java 17** |

**Cẩn thận khi đọc output:** `HttpClient.Version.HTTP_2` là **ưu tiên/phiên bản HTTP**; khi kết nối server không hỗ trợ, Java HttpClient có thể fallback xuống HTTP/1.1. Hãy đọc `HttpResponse.version()` để biết version thực tế. Java 17 `HttpClient` không có `HTTP_3` enum, nên ví dụ bài này **ép HTTP/1.1** để minh họa rõ format và semantics.

## 9. HTTPS thêm TLS ở đâu? HTTP có thay TCP/QUIC không?

URI scheme thường thấy:

- `http://example.test/path`: HTTP thông thường qua transport đã cấu hình (trên web HTTP/1.1 qua TCP); **không** cung cấp mã hóa TLS theo scheme này.
- `https://example.test/path`: HTTP qua kết nối được bảo mật; phổ biến là HTTP/1.1 hoặc HTTP/2 trên TLS/TCP, hoặc HTTP/3 trên QUIC bảo mật tích hợp.

Với HTTPS over TCP:

~~~text
HTTP request/response
       |
       v
HTTP encoding/framing
       |
       v
TLS records (encryption, integrity, server authentication)
       |
       v
TCP byte stream
       |
       v
IP packets
~~~

Trình tự điển hình: DNS → TCP connection → TLS handshake (ALPN có thể thương lượng `http/1.1` hoặc `h2`) → HTTP request/response → connection reuse hoặc close.

HTTP/3 trên QUIC không xếp nguyên một lớp TLS record giống TLS/TCP; QUIC dùng TLS 1.3 cho thiết lập khóa/bảo mật nhưng tích hợp khác trong transport. **Không** mô tả HTTP/3 là `TLS/TCP` hoặc “chạy UDP trần”.

**HTTPS giúp bảo mật đường truyền, không thay authentication/authorization nghiệp vụ.** Có TLS vẫn phải kiểm tra user có quyền đọc `/users/7`, tránh lộ API key và không tin đầu vào client.

## 10. Java 17+ — Demo đầy đủ: HTTP server và HttpClient loopback

Ví dụ dùng **server HTTP nhỏ có sẵn trong module `jdk.httpserver`** và **client HTTP chuẩn `java.net.http.HttpClient`**.

Mục tiêu:

- Server có resource `/demo`; GET trả message, POST đọc request body và trả message phản hồi.
- Client tạo `HttpRequest` chứa method, URI, body và timeout.
- `HttpClient` thực hiện transport, HTTP serialization/parsing, message framing; ứng dụng chỉ tập trung vào **HTTP semantics**.
- In ra status code, body và HTTP version. Server bind loopback với port `0`, nên không cần cổng bên ngoài.

**Tệp `HttpRequestResponseDemo.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpRequestResponseDemo {
    private static void handle(HttpExchange exchange) throws java.io.IOException {
        try (exchange) {
            String method = exchange.getRequestMethod();
            String result;
            if (method.equals("GET")) {
                result = "Hello from HTTP";
            } else if (method.equals("POST")) {
                byte[] input = exchange.getRequestBody().readAllBytes();
                result = "Echo: " + new String(input, StandardCharsets.UTF_8);
            } else {
                exchange.getResponseHeaders().set("Allow", "GET, POST");
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            byte[] bytes = result.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/demo", HttpRequestResponseDemo::handle);
        server.start();
        try {
            URI endpoint = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/demo");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest get = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> first = client.send(
                    get, HttpResponse.BodyHandlers.ofString());
            System.out.println("GET: " + first.statusCode() +
                    " | " + first.body());

            HttpRequest post = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString("ping"))
                    .build();
            HttpResponse<String> second = client.send(
                    post, HttpResponse.BodyHandlers.ofString());
            System.out.println("POST: " + second.statusCode() +
                    " | " + second.body());
            System.out.println("Version: " + second.version());
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Lệnh biên dịch/chạy bằng JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HttpRequestResponseDemo.java
java --add-modules jdk.httpserver HttpRequestResponseDemo
~~~

**Stdout được biên dịch và chạy thực tế với OpenJDK 24, dùng `--release 17` để kiểm tra API Java 17:**

~~~text
GET: 200 | Hello from HTTP
POST: 200 | Echo: ping
Version: HTTP_1_1
~~~

### 10.1. Từng phần thể hiện lớp HTTP nào?

1. `HttpServer.create(new InetSocketAddress(..., 0), 0)` tạo server trên loopback port OS chọn. Đây là **transport endpoint**.
2. `server.createContext("/demo", ...)` liên kết **HTTP resource path** và handler ứng dụng. TCP không tự có khái niệm “context /demo”.
3. `exchange.getRequestMethod()` đọc **HTTP method**, không phải `Socket` flag.
4. `exchange.getRequestBody()` đọc bytes của **HTTP request body** đã được HTTP implementation giải mã/framing. Trong ứng dụng thật phải **giới hạn body size**; demo dùng `readAllBytes()` chỉ vì payload nhỏ do chính chương trình gửi.
5. `getResponseHeaders().set("Content-Type", ...)` mô tả media type của representation.
6. `sendResponseHeaders(200, bytes.length)` tạo **HTTP status/header + response framing**; body được ghi bằng output stream. `bytes.length` chính là số byte UTF-8 đã mã hóa.
7. `HttpRequest.newBuilder(endpoint).GET()` và `POST(BodyPublishers.ofString("ping"))` biểu diễn **intent** của client; thư viện tự gửi request đúng HTTP syntax.
8. `HttpResponse.statusCode()` và `body()` cho kết quả ở tầng HTTP, không yêu cầu application tự parse raw CRLF.
9. `second.version()` cho biết giao thức thực đã sử dụng, là `HTTP_1_1` vì demo đặt ưu tiên HTTP/1.1.
10. `server.stop(0)` giải phóng HTTP server ở cuối. Java `HttpClient` trên **Java 17 không implement `AutoCloseable`**, nên demo không dùng `try (HttpClient client=...)`; đó là khác biệt API quan trọng khi dùng JDK 17.

**Phạm vi demo:** `com.sun.net.httpserver.HttpServer` là server nhúng tối giản phục vụ mục đích học tập/thử nghiệm, **không phải** giải pháp production mặc định cho public Internet hoặc API yêu cầu bảo mật/quan sát cao. Code cố ý không có authentication, request body limit, concurrency tuning, TLS hoặc logging. Nếu chạy trên máy mà loopback mặc định ưu tiên IPv6 khiến URI cố định `127.0.0.1` không khớp interface server bind, hãy dùng địa chỉ IPv4 loopback được bind rõ ràng hoặc dựng URI IPv6 đúng cú pháp; không mở listener ra toàn mạng chỉ để tránh lỗi test.

## 11. Java 17+ — Demo đầy đủ: đọc HTTP/1.1 trực tiếp qua TCP Socket

Ví dụ trước sử dụng thư viện HTTP nên không thấy HTTP message bytes. Ví dụ này cố ý dùng **`ServerSocket` và `Socket` thuần**, tự đọc header request và viết response HTTP/1.1. Nó **chỉ hỗ trợ một GET không có body**, không có TLS, không có persistent connection và **không phải HTTP parser hoàn chỉnh**.

Nó giúp chứng minh: **TCP chỉ chuyển byte; ứng dụng phải chủ động áp dụng cấu trúc/semantics HTTP để người nhận hiểu request/response.**

**Tệp `RawHttpOverTcpDemo.java`:**

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RawHttpOverTcpDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket(
                0, 8, InetAddress.getLoopbackAddress())) {
            server.setSoTimeout(5000);
            Future<String> observed = worker.submit(() -> {
                try (Socket accepted = server.accept()) {
                    accepted.setSoTimeout(5000);
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(
                                    accepted.getInputStream(),
                                    StandardCharsets.US_ASCII));
                    String startLine = reader.readLine();
                    String header;
                    while ((header = reader.readLine()) != null && !header.isEmpty()) {
                        // Consume the rest of the HTTP/1.1 header section.
                    }
                    if (header == null || startLine == null) {
                        throw new IllegalStateException("Incomplete request");
                    }
                    byte[] reply = (
                            "HTTP/1.1 200 OK\r\n" +
                            "Content-Type: text/plain\r\n" +
                            "Content-Length: 4\r\n" +
                            "Connection: close\r\n\r\n" +
                            "PONG").getBytes(StandardCharsets.US_ASCII);
                    accepted.getOutputStream().write(reply);
                    accepted.getOutputStream().flush();
                    return startLine;
                }
            });

            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(), server.getLocalPort())) {
                client.setSoTimeout(5000);
                byte[] request = (
                        "GET /ping HTTP/1.1\r\n" +
                        "Host: localhost\r\n" +
                        "Connection: close\r\n\r\n")
                        .getBytes(StandardCharsets.US_ASCII);
                client.getOutputStream().write(request);
                client.getOutputStream().flush();
                String response = new String(
                        client.getInputStream().readAllBytes(),
                        StandardCharsets.US_ASCII);
                System.out.println("Response status: " +
                        response.substring(0, response.indexOf("\r\n")));
                System.out.println("Response body: " +
                        response.substring(response.indexOf("\r\n\r\n") + 4));
            }
            System.out.println("Server request: " +
                    observed.get(5, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

**Lệnh biên dịch/chạy:**

~~~bash
javac --release 17 -encoding UTF-8 RawHttpOverTcpDemo.java
java RawHttpOverTcpDemo
~~~

**Stdout đã biên dịch/chạy thành công:**

~~~text
Response status: HTTP/1.1 200 OK
Response body: PONG
Server request: GET /ping HTTP/1.1
~~~

### 11.1. Vì sao server và client đều cần thêm mã HTTP?

- TCP server nhận connection qua `accept()`, nhưng **không tự trả `200 OK`**. Worker viết literal bytes của status line và HTTP headers.
- Client gửi các byte cho method, request target, version, `Host` và `Connection`. Nếu gửi mỗi `PING` qua TCP thì **không phải** một HTTP/1.1 request hợp lệ.
- Worker đọc request start-line và lặp header đến dòng trống để tìm vị trí bắt đầu body; code demo **không đọc body request**, vì GET demo không gửi body.
- Response gửi `Content-Length: 4` bởi body `PONG` dài bốn byte ASCII; `Connection: close` giúp client `readAllBytes()` tới EOF kết thúc sau response.
- Client tự tìm `\r\n` và `\r\n\r\n` để in. Đây **chỉ là cách kiểm chứng format của ví dụ**, không đủ dùng để parse một arbitrary response HTTP/1.1 (chunking, interim responses, encoding, malformed input, header limits, pipelining...).
- Với persistent connection, `readAllBytes()` có thể đợi vô hạn; phải dùng framing đúng. Không nên copy kiểu parse bằng `substring(...)` để tạo HTTP client production.

**Vì sao ví dụ raw chỉ học tập?** Nó bỏ qua routing đầy đủ, validation target, giới hạn header/body, chunked encoding, `Expect: 100-continue`, keep-alive, HTTP method semantics và request smuggling defenses. Production hãy dùng `HttpClient`, server HTTP framework hoặc implementation đã được kiểm chứng thay vì tự tạo parser.

## 12. Phân biệt lỗi transport, TLS, HTTP và business

Một request có thể thất bại ở nhiều tầng; cách retry và thông báo cho người dùng phụ thuộc lỗi xảy ra ở đâu.

~~~text
Client bắt đầu gọi https://api.example.test/orders/1
    |
    +-- DNS lookup thất bại
    |     -> chưa mở TCP/QUIC; chưa có HTTP status
    |
    +-- TCP connect timeout / connection refused
    |     -> transport chưa hoàn tất; chưa có HTTP response
    |
    +-- TLS certificate invalid / handshake fail
    |     -> phiên bảo mật không thành công; chưa có HTTP status cuối
    |
    +-- HTTP server trả 401/403/404/500/503
    |     -> đã có HTTP response ở tầng ứng dụng
    |
    +-- HTTP 200 nhưng JSON lỗi business (nếu thiết kế API như vậy)
          -> phải xét contract API, không suy diễn từ TCP/TLS success
~~~

**Quy tắc kiểm tra:**

- `ConnectException`, `UnknownHostException`, `SSLHandshakeException`, `HttpTimeoutException` là những lỗi **không đồng nhất với status code**.
- `HttpClient.send(...)` bình thường **trả về `HttpResponse` cho status 4xx/5xx**; Java HttpClient không tự throw chỉ vì server trả HTTP 404 hoặc 500. Application nên kiểm tra `response.statusCode()`.
- Response `503 Service Unavailable` là tín hiệu HTTP; retry có thể hợp lý với delay/backoff hoặc `Retry-After`, nhưng phải xét an toàn khi lặp request.
- Connection bị cắt **sau khi client gửi POST** tạo ra trường hợp không biết server có xử lý xong nghiệp vụ hay chưa. Retry tự động có thể **tạo đơn hàng trùng**; dùng idempotency key hoặc kiểm tra kết quả bằng resource id nếu thiết kế yêu cầu.
- TLS certificate failure không nên khắc phục bằng cách “tạm tắt kiểm tra TLS” ở production.

### 12.1. Timeout ở cấp nào?

| Timeout | Ý nghĩa | Ví dụ Java |
| --- | --- | --- |
| DNS resolution | Thời gian giải tên | Thường phụ thuộc resolver/OS; không đồng nhất connectTimeout |
| TCP connect | Đợi thiết lập kết nối | `HttpClient.Builder.connectTimeout(Duration)` |
| HTTP request tổng | Đợi request–response hoàn tất theo contract API | `HttpRequest.Builder.timeout(Duration)` |
| Read idle / ứng dụng | Không có byte đủ điều kiện trong hạn | Có thể yêu cầu timeout policy riêng theo server/client library |
| Proxy/gateway | Chờ upstream | Có thể xuất hiện `504 Gateway Timeout` |
| Business deadline | Giới hạn xử lý đơn hàng/tác vụ | Cần thiết kế app và cancellation riêng |

Một timeout **không** chứng minh server chưa thực hiện side effect. Càng không thể dùng HTTP 200 hoặc TCP ACK làm bằng chứng một thao tác kinh doanh bất đồng bộ đã commit.

## 13. Cache và conditional requests cũng là khả năng HTTP bổ sung

Transport thường không biết “response này đã cũ” hay “có thể dùng dữ liệu lưu lần trước”. HTTP có header và semantics cho caching.

Ví dụ ý tưởng:

~~~http
GET /articles/10 HTTP/1.1
Host: example.test
If-None-Match: "v7"

~~~

Nếu representation chưa thay đổi theo điều kiện validator, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "v7"
Cache-Control: max-age=120

~~~

Client/cache dùng representation đã lưu theo các điều kiện của HTTP caching; **304 không có body mới**. Đây là điểm TCP không thể tự suy ra.

Các thuật ngữ:

- **Freshness**: response có thể sử dụng lại theo cache policy (ví dụ `max-age`).
- **Validation**: kiểm tra bản đã lưu còn phù hợp qua `ETag`/`If-None-Match` hoặc `Last-Modified`/`If-Modified-Since`.
- **Private vs shared cache**: dữ liệu cá nhân cần chính sách `private` hoặc `no-store` phù hợp, tránh proxy công cộng lưu thông tin nhạy cảm.
- **Vary**: cache key chịu ảnh hưởng một số request header được chỉ định.
- **Unsafe methods** có thể làm cached representation lỗi thời hoặc cần invalidation.

Dùng cache đúng giúp giảm request/response size và latency, nhưng sai cache policy có thể làm lộ nội dung riêng tư. Không tự hiểu “GET luôn được cache” hay “có TLS thì không được cache”: phải xem HTTP caching semantics và headers.

## 14. Proxy, reverse proxy, gateway vẫn trao đổi HTTP semantics

Một request có thể đi qua nhiều thành phần:

~~~text
Browser / Java HttpClient
        |
        v
Forward proxy (nếu cấu hình)
        |
        v
Reverse proxy / load balancer / gateway
        |
        +------ HTTP/1.1 tới backend A
        |
        +------ HTTP/2 tới backend B
        |
        v
Origin application
~~~

- **Forward proxy** đại diện client về phía server; dùng cho policy, routing hoặc cache.
- **Reverse proxy** đại diện hệ thống server, nhận request ở edge rồi chuyển tới backend; có thể terminate TLS, load balance, áp dụng auth/rate limiting.
- **Gateway** có thể chuyển đổi giữa giao thức hoặc giữa các phiên bản HTTP.
- **Origin server** chịu trách nhiệm cuối về resource semantics (dù response có thể được cache hoặc tạo bởi intermediary).

HTTP giúp intermediary hiểu method, target, headers, cache controls và status để xử lý ở cấp application. TCP router không tự biết request `/health` có thể cache hay không. Tuy nhiên một **hop** HTTP có thể dùng một connection/version khác hop kế tiếp. Ví dụ client dùng HTTP/2 tới reverse proxy, proxy dùng HTTP/1.1 tới backend. Đừng suy diễn version backend chỉ từ version client.

Các header **hop-by-hop** như `Connection` trong HTTP/1.1 cần được xử lý đúng qua proxy; không chuyển chúng như end-to-end headers. Không tin `X-Forwarded-For`/`Forwarded` từ client tùy ý: chỉ chấp nhận từ proxy tin cậy theo cấu hình.

## 15. Tác động thực tế với Java Networking

### 15.1. Khi nào dùng `Socket` thuần?

Dùng `Socket` / `ServerSocket` khi:

- Thiết kế giao thức byte stream riêng (nhưng vẫn cần framing, versioning, auth, timeouts).
- Học mạng cơ bản hoặc debug transport.
- Viết adapter/protocol khác HTTP, ví dụ một giao thức binary được định nghĩa cụ thể.
- Cần kiểm thử raw wire messages ở môi trường được phép kiểm soát.

**Không** dùng `Socket` chỉ để tự lắp HTTP cho một API thông thường. Khi tự lập HTTP serializer/parser, bạn gánh trách nhiệm framing, encoding, security, keep-alive, redirects, TLS, proxy, compression, HTTP/2/3 compatibility và compliance.

### 15.2. Khi nào dùng `java.net.http.HttpClient`?

Java 17 `HttpClient` cung cấp:

- `HttpRequest` builder: URI, method, headers, body publisher, timeout.
- `HttpResponse`: status, headers, body, version.
- `BodyPublishers`/`BodyHandlers` cho bytes, strings, files và nhiều kiểu khác.
- `send()` đồng bộ; `sendAsync()` trả `CompletableFuture` cho xử lý bất đồng bộ.
- HTTP/1.1 và HTTP/2 theo API, connection reuse, redirects và proxy/TLS options được cấu hình.
- Tránh ứng dụng phải tự viết CRLF hoặc xử lý `Content-Length` thủ công.

Ví dụ ngắn (mảnh minh họa trong method `throws Exception`):

~~~java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/data"))
    .header("Accept", "application/json")
    .timeout(Duration.ofSeconds(5))
    .GET()
    .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

int status = response.statusCode();
String contentType = response.headers()
        .firstValue("Content-Type").orElse("unknown");
String body = response.body();
~~~

Cần imports `java.net.URI`, `java.net.http.*` và `java.time.Duration`; URL chỉ minh họa, **không** có stdout/bảo đảm endpoint trả JSON. Không biến `Content-Type` response thành giá trị xác thực tuyệt đối: vẫn cần parse/validate body, giới hạn size và xử lý lỗi. Java HttpClient không đảm bảo server hỗ trợ HTTP/2 chỉ vì client ưu tiên phiên bản đó.

### 15.3. Tại sao HTTP server không giống TCP server?

Server TCP thường có loop `accept() -> Socket -> InputStream/OutputStream`. HTTP server còn phải:

- Giải mã/chấp nhận HTTP version và framing.
- Nhận diện URI/Host/authority, HTTP method và request target.
- Áp dụng giới hạn header/body, timeout và policy security.
- Ánh xạ resource tới handler/method cụ thể.
- Đọc representation theo media type; validate dữ liệu.
- Xác thực/kiểm tra authorization.
- Sinh status, headers, body với framing hợp lệ.
- Xử lý persistent connection, concurrency, proxies, errors/cancellation.
- Theo dõi request-id, latency, success/failure ở cấp HTTP.

Vì vậy **không chỉ thêm `GET` vào chuỗi TCP** là đã có HTTP server đầy đủ. Trong ứng dụng thực, dùng server HTTP được duy trì/bảo trì, tránh lập parser tay.

## 16. Bảo mật và các giả định nguy hiểm

1. **HTTPS không thay authorization.** TLS bảo vệ đường truyền và thường xác thực server, nhưng application vẫn phải xác định quyền user/resource.
2. **Đừng tự parse HTTP trong production**: HTTP/1.1 có nhiều quy tắc framing và sự khác biệt parser giữa proxies có thể tạo request smuggling.
3. **Giới hạn input**: header size/count, URI length, body size, upload size, decompression ratio, request duration, concurrent connections và active requests; demo dùng `readAllBytes()` chỉ khi payload có giới hạn do chính code kiểm soát.
4. **Tránh SSRF**: server không nên tùy tiện fetch bất kỳ URL do client đưa nếu có thể tới metadata/internal services.
5. **Không tin `Host`, forwarded headers hoặc client-set `Content-Length`** nếu chúng ảnh hưởng routing/security; để HTTP stack parse và thực thi policy đúng.
6. **Cookie và token** cần bảo vệ: `Secure`, `HttpOnly`, `SameSite` đúng mục đích, thời hạn hợp lý, không log secrets hoặc gửi token qua HTTP thuần.
7. **Retry** cần xét idempotency và business side effects; `GET` safe được kỳ vọng, `POST` mặc định không nên retry mù quáng nếu outcome chưa biết.
8. **Cache** có thể làm lộ dữ liệu cá nhân nếu shared cache chứa response cần riêng tư; cấu hình `Cache-Control` và token/vary đúng.
9. **HTTP response 200 không phải bảo đảm transaction distributed**; hợp đồng ứng dụng phải nêu rõ trạng thái hoàn tất.
10. **HTTP/3 không phải UDP không bảo mật**; nó là HTTP semantics trên QUIC, có transport security và stream semantics.

## 17. Các nhầm lẫn nền tảng thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| “TCP đã biết HTTP request/response” | TCP biết byte stream; HTTP xác định message và semantics |
| “Một HTTP message bằng một TCP packet” | Không; TCP có thể chia/gộp bytes tự do |
| “Một HTTP request luôn tạo TCP connection mới” | Không; HTTP/1.1 reuse, HTTP/2/3 multiplex |
| “HTTP là TCP protocol nên HTTP/3 cũng chạy TCP” | HTTP/3 là mapping qua QUIC/UDP |
| “HTTP/3 dùng UDP nên body có thể đảo byte như datagram” | QUIC cung cấp reliable in-order data trên từng stream |
| “HTTP/2 là HTTP/1.1 text thêm nén” | HTTP/2 dùng binary framing, streams và HPACK |
| “HTTP method là network command của OS” | Method thuộc semantics của HTTP ở tầng ứng dụng |
| “GET luôn là không có side effect và không cần auth” | Safe semantics không xóa logging và authorization |
| “PUT idempotent nên response mỗi lần phải y chang” | Idempotent nói về hiệu ứng dự kiến trên resource |
| “POST không thể retry” | Có thể retry khi đã thiết kế idempotency/deduplication hoặc biết rõ an toàn |
| “TCP ACK nghĩa là server đã lưu đơn hàng” | TCP ACK chỉ xác nhận nhận byte ở tầng transport, không chứng minh business commit |
| “HTTP 404 là lỗi TCP không kết nối được” | 404 là một HTTP response; lỗi connect không có HTTP status |
| “HTTP 500 làm Java HttpClient tự ném exception” | `HttpClient.send()` thường trả `HttpResponse`; kiểm tra status |
| “Content-Length là số chữ trong Java String” | Đó là số byte content theo wire framing |
| “Một lần read() đủ hết response” | TCP stream partial reads; HTTP parser cần framing |
| “Content-Type và Accept là cùng một loại header” | `Content-Type` mô tả representation gửi; `Accept` diễn tả mong muốn nhận |
| “HTTP stateless nghĩa là không đăng nhập được” | Session/cookie/token là state ở tầng ứng dụng |
| “Connection: close là header dùng như nhau ở HTTP/2/3” | HTTP/2/3 có quy tắc frame/connection khác; connection-specific headers không hợp lệ như trong h1 |
| “Có HTTPS nên không cần kiểm tra user permission” | TLS không thay authorization |
| “Proxy chỉ là router IP thông thường” | Proxy hiểu/điều phối HTTP messages và đôi khi thay đổi transport/version giữa hops |
| “Client HTTP/2 gửi tới server HTTP/1.1 chắc chắn thất bại” | HTTP client có thể thương lượng/fallback đúng chuẩn; xem version thực nhận |
| “Có HttpClient là Java 17 tự hỗ trợ HTTP/3” | API chuẩn Java 17 hỗ trợ HTTP/1.1 và HTTP/2, không có HTTP/3 enum |

## 18. Bài tập thực hành và đáp án

### Bài 1 — So sánh TCP và HTTP

Một chương trình TCP gửi dòng byte `"PING"` đến port 9000. Có thể gọi đó là HTTP request không?

**Đáp án:** Không, trừ khi chương trình áp dụng đúng HTTP message framing và semantics. `PING` chỉ là payload TCP; một HTTP/1.1 request cần method, target, version, headers đúng cấu trúc như `GET /ping HTTP/1.1` với `Host` và kết thúc header bằng CRLF CRLF.

### Bài 2 — Phân biệt request/response

Đọc thông điệp:

~~~http
POST /notes HTTP/1.1
Host: example.test
Content-Type: application/json
Content-Length: 13

{"text":"hi"}
~~~

Hãy chỉ ra method, resource target, request header và request body.

**Đáp án:** Method `POST`, target `/notes`, header gồm `Host`, `Content-Type` và `Content-Length`, body là JSON `{"text":"hi"}` đúng 13 byte ASCII. TCP không hiểu việc tạo note; semantics do HTTP + application định nghĩa.

### Bài 3 — Status không phải transport error

Client gọi một API và nhận `HTTP/1.1 404 Not Found`; client khác nhận `ConnectException`. Hai tình huống khác gì nhau?

**Đáp án:** Trường hợp 404 đã có **HTTP response** hợp lệ báo không tìm thấy resource; `ConnectException` xảy ra ở tầng thiết lập transport nên thường chưa có HTTP response. Recovery/logging nên phân loại khác.

### Bài 4 — Persistence

Server HTTP/1.1 đã trả response A nhưng TCP connection vẫn mở. Client có nên chờ `readAllBytes()` đến EOF để xác định response A đã xong không?

**Đáp án:** Không. Connection persistent có thể tiếp tục mang request/response khác; dùng HTTP/1.1 framing (content length/chunked/semantics) để biết ranh giới A.

### Bài 5 — HTTP/2 và HTTP/3

Sự khác biệt nền tảng giữa hai version về transport là gì? GET/POST và HTTP 200 có phải học lại ngữ nghĩa từ đầu không?

**Đáp án:** HTTP/2 truyền binary frames và multiplex streams qua TCP; HTTP/3 dùng QUIC trên UDP với streams đáng tin cậy và TLS 1.3 tích hợp. Semantics chung (method, resource, status, representation) vẫn được giữ theo HTTP chuẩn.

### Bài 6 — Idempotent

Hai request PUT giống nhau tới resource `/settings/theme` có thể trả 201 lần đầu và 200 lần sau, vậy còn idempotent không?

**Đáp án:** Có thể còn idempotent, vì điều kiện xét là **hiệu ứng dự kiến lên resource khi lặp lại** chứ không phải status code hay response từng lần phải giống nhau. Nhưng implementation phải tránh side effect không idempotent ngoài ý muốn.

### Bài 7 — POST timeout

Client gửi POST tạo đơn hàng, sau đó connection rớt trước khi thấy response. Có thể khẳng định server chưa tạo đơn rồi retry ngay không?

**Đáp án:** Không. Outcome không rõ vì server có thể đã thực hiện thành công rồi response bị mất. Nên thiết kế idempotency key, operation ID hoặc API kiểm tra kết quả; retry có kiểm soát.

### Bài 8 — Cache validation

Client gửi `If-None-Match: "v7"` và server trả `304 Not Modified`. Client nên hiểu thế nào?

**Đáp án:** Server báo representation không thay đổi theo validator; cache/client có thể tái sử dụng representation đã lưu theo HTTP caching rules. `304` không chứa body mới tương đương một `200` response đầy đủ.

### Bài 9 — Content-Length và Unicode

Response có body `"Việt"`, được mã hóa UTF-8. Tại sao không dùng `String.length()` trực tiếp làm `Content-Length`?

**Đáp án:** Vì `Content-Length` tính theo **byte**, trong khi Java `String.length()` tính UTF-16 code units. Phải mã hóa text thành bytes và lấy `bytes.length` theo charset đã chọn.

### Bài 10 — Java HttpClient và HTTP 404

Trong Java 17, `client.send(req, BodyHandlers.ofString())` nhận HTTP 404. Có bắt buộc method ném exception vì 404 không?

**Đáp án:** Không. Nó thường trả `HttpResponse` với `statusCode() == 404`; caller tự quyết định đây là lỗi theo nghiệp vụ. Ngoại lệ được dùng cho các lỗi I/O, timeout, interruption và lỗi khác không phải chỉ vì status code là 4xx/5xx.

### Bài 11 — Request–response không đồng nghĩa synchronous API

HTTP request–response có ngăn client Java sử dụng `sendAsync()` hoặc server xử lý background job không?

**Đáp án:** Không. Request–response mô tả **ngữ nghĩa tương tác**. API Java vẫn có thể bất đồng bộ; server có thể trả `202 Accepted` kèm URI theo dõi một job đang chạy. Đừng nhầm mô hình message với blocking thread.

### Bài 12 — Proxy thay transport

Client dùng HTTP/2 qua TLS tới reverse proxy, proxy dùng HTTP/1.1 tới backend. Có phải GET biến thành ý nghĩa khác?

**Đáp án:** Không. Proxy/gateway phải bảo toàn hoặc áp dụng chuyển đổi hợp lệ cho **HTTP semantics** giữa các hops. Representation/framing/transport có thể khác nhau, nhưng client vẫn đang yêu cầu cùng resource/method theo hợp đồng API.

## 19. Checklist học và triển khai HTTP trên Java

- [ ] Tôi phân biệt TCP byte stream, TLS/QUIC transport và HTTP message semantics.
- [ ] Tôi hiểu resource/URI, method, header, status và response body thuộc lớp HTTP.
- [ ] Tôi biết HTTP/1.1 dùng start lines + CRLF + headers + body, cần framing chính xác.
- [ ] Tôi không giả định một `read()` bằng một HTTP request/response.
- [ ] Tôi biết `Content-Length` là byte length và khi nào response không có body.
- [ ] Tôi biết HTTP/2 có binary frames/multiplexing, HTTP/3 qua QUIC streams, không phải raw UDP text.
- [ ] Tôi hiểu HTTP stateless khác với session/cookies và connection persistence.
- [ ] Tôi phân biệt `safe` và `idempotent` trước khi thiết kế retry.
- [ ] Tôi kiểm tra `HttpResponse.statusCode()`; không coi 4xx/5xx là `Socket` exception.
- [ ] Tôi cấu hình connect/request timeout và giới hạn body, headers, concurrency.
- [ ] Tôi không tự viết HTTP parser cho production chỉ vì biết CRLF.
- [ ] Tôi chọn HTTPS cho thông tin nhạy cảm và kiểm tra certificate, authorization, input validation.
- [ ] Tôi hiểu proxy có thể thay HTTP version/connection trên từng hop.
- [ ] Tôi có kế hoạch caching, conditional requests, retry và observability phù hợp.
- [ ] Tôi biết Java 17 `HttpClient` hỗ trợ HTTP/1.1/2, không hỗ trợ HTTP/3 qua API chuẩn.
- [ ] Tôi dùng thư viện HTTP đầy đủ cho API thông thường; chỉ dùng raw socket ở bài lab/protocol riêng.

## 20. Tài liệu tham khảo tiêu chuẩn và Java

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): định nghĩa request/response, application-level stateless semantics, resource/method/status/headers và các HTTP versions.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request line, status line, CRLF, message syntax và framing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): binary frames, streams, multiplexing, header compression HPACK.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP semantics trên QUIC, streams và HTTP/3 framing.
- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000): transport reliability, streams và connection management.
- [RFC 9204 — QPACK](https://www.rfc-editor.org/rfc/rfc9204): field compression cho HTTP/3.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache freshness, validation, reuse và shared cache.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): xây client HTTP, version, timeouts, `send` và `sendAsync`.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): method, URI, headers, body publisher.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status, body, version, headers.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server nhúng để học/test, `HttpExchange`, routing context.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): byte stream TCP; dùng làm nền so sánh với HTTP semantics.

**Kết luận:** Transport giúp dữ liệu đi giữa hai đầu, còn **HTTP định nghĩa client đang yêu cầu điều gì và server phản hồi như thế nào** qua resource, method, status, header, content và quy tắc message. **HTTP/1.1, HTTP/2, HTTP/3 bảo toàn những semantics cốt lõi này nhưng khác transport và framing**. Với Java, dùng `HttpClient`/HTTP server để làm việc ở tầng ứng dụng; chỉ dùng raw socket khi cần nghiên cứu hoặc tự triển khai một protocol đã được định nghĩa chặt chẽ.
