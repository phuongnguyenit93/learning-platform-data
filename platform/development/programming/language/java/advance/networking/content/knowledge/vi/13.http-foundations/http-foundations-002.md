# Method, URI đích, header, mã trạng thái và body

## Mục tiêu bài học

HTTP (*Hypertext Transfer Protocol*) là giao thức ở tầng ứng dụng cho mô hình **request/response**. Đọc một giao dịch HTTP cho đúng nghĩa là phải tách được **method**, **URI đích** và **header/body** của request; đồng thời đọc **status code**, **header/body** của response. Các thành phần này có vai trò khác nhau: method nêu ý định, URI định vị tài nguyên, header mang metadata và thông tin điều khiển, status mô tả kết quả ở mức giao thức, còn body là nội dung biểu diễn hoặc dữ liệu được truyền.

Sau bài học, bạn có thể:

- Đọc và viết cấu trúc request/response HTTP/1.1; hiểu các thành phần vẫn có ý nghĩa trong HTTP/2 và HTTP/3 dù dạng truyền trên dây khác.
- Phân biệt semantics của `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE` và `OPTIONS`; nhận biết *safe* và *idempotent* không đồng nghĩa.
- Nhận dạng URI đích, path, query, authority và fragment; hiểu dạng request-target của HTTP/1.1 và ý nghĩa `Host`/`:authority`.
- Dùng đúng `Content-Type`, `Accept`, `Content-Length`, `Authorization`, `Location`, `Cache-Control`, `ETag`; nhận biết header names không phân biệt hoa/thường.
- Giải thích nhóm mã trạng thái `1xx` đến `5xx`, đặc biệt các code hay gặp như `200`, `201`, `204`, `301`, `304`, `400`, `401`, `403`, `404`, `405`, `409`, `415`, `429`, `500` và `503`.
- Phân biệt **payload body**, **representation metadata**, độ dài **byte trên wire**, encoding và ranh giới thông điệp.
- Chạy ví dụ Java 17+ có HTTP server/client trên loopback để quan sát method, target URI, header, status và response body.
- Tránh các lỗi bảo mật/phân tích như nhầm query với body, parse HTTP bằng `readLine` tùy tiện, tin `Host` vô điều kiện, log token, xử lý `Content-Length`/`Transfer-Encoding` mâu thuẫn.

**Phạm vi:** nền tảng HTTP với HTTP/1.1 là cách trình bày text trực quan; HTTP/2 và HTTP/3 giữ phần lớn semantics nhưng dùng frame và header compression khác. Ví dụ Java dùng JDK 17, không yêu cầu Internet.

## 1. Một cuộc trao đổi HTTP gồm những gì?

Ở mức khái niệm:

~~~text
Client                             Server
  │                                  │
  ├── HTTP Request ─────────────────►│
  │   Method + URI đích              │
  │   Header fields                  │
  │   (Body nếu có)                  │
  │                                  │
  │◄───────────────── HTTP Response ─┤
  │                    Status code   │
  │                    Header fields │
  │                    (Body nếu có) │
~~~

### Request trong HTTP/1.1

Ví dụ minh họa một request:

~~~http
POST /api/notes?notify=true HTTP/1.1
Host: example.org
Content-Type: application/json; charset=utf-8
Accept: application/json
Content-Length: 16

{"title":"Java"}
~~~

Các dòng trên được trình bày bằng newline cho dễ đọc; **HTTP/1.1 thực tế dùng CRLF** (`\r\n`) ở cuối start-line/header-line và một dòng trống `\r\n` để kết thúc phần header. Body có thể là bytes tùy định dạng, không nhất thiết là text.

Phân tích:

- `POST`: **method** của request.
- `/api/notes?notify=true`: **request-target** ở dạng `origin-form`; gồm path và query.
- `HTTP/1.1`: phiên bản HTTP của start-line.
- `Host`: hostname/authority đích, đặc biệt quan trọng khi một server phục vụ nhiều virtual hosts.
- `Content-Type`: định dạng **body mà client gửi lên** — trong ví dụ JSON UTF-8.
- `Accept`: kiểu representation mà client muốn nhận.
- `Content-Length: 16`: có **16 byte** payload trong ví dụ ASCII `{"title":"Java"}` (không tính dòng trống phân cách); không phải độ dài toàn bộ request.
- Dòng trống sau header: đánh dấu hết header, bắt đầu body.
- `{"title":"Java"}`: **request body** chứa representation của nội dung được gửi, không phải thành phần của URI.

Lưu ý: `Content-Length: 16` đúng với **16 byte UTF-8** của chuỗi ví dụ, vì các ký tự đều ASCII. Nếu body chứa tiếng Việt/emoji, không được dùng `String.length()` để điền số byte.

### Response trong HTTP/1.1

~~~http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /api/notes/42
Content-Length: 14

{"id":42}
~~~

**Ví dụ trên chỉ minh họa cú pháp, không phải giá trị Content-Length để dùng lại:** body `{"id":42}` thực tế dài **9 byte**, vì vậy một response HTTP/1.1 hợp lệ phải ghi `Content-Length: 9` (hoặc dùng cơ chế framing khác hợp lệ). Hãy xem ví dụ sửa đúng:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /api/notes/42
Content-Length: 9

{"id":42}
~~~

Ở response:
- `201` là **status code** cho kết quả tạo tài nguyên.
- `Created` là reason phrase minh họa trong HTTP/1.1; **code mới quyết định semantics**. Reason phrase có thể thay đổi và HTTP/2/3 không mang reason phrase theo kiểu start-line text.
- `Location` chỉ ra URI của tài nguyên mới, có thể là URI tương đối như `/api/notes/42`.
- `Content-Type` mô tả representation của **response body**.
- Body `{"id":42}` là JSON được ứng dụng trả về; không phải trạng thái HTTP.

**Điểm mấu chốt:** method/URI/header/status/body là các **khái niệm nghiệp vụ và giao thức tách biệt**. Server có thể trả `404` cùng một body JSON giải thích lỗi; body nói chi tiết, status nói kết quả HTTP chuẩn hóa.

## 2. Method: hành động mong muốn và semantics

HTTP method là token trong request, ví dụ `GET` hoặc `POST`. **Method names phân biệt hoa/thường** theo chuẩn; nên dùng dạng chuẩn toàn chữ hoa, không viết `get` rồi giả định tương đương.

| Method | Ý nghĩa điển hình | Request body? | Safe? | Idempotent? |
|---|---|---|---|---|
| `GET` | Lấy representation/trạng thái của resource | Không có semantics chung được quy định cho nội dung trong GET body; tránh dùng | Có | Có |
| `HEAD` | Như GET nhưng không truyền response content/body | Thường không cần | Có | Có |
| `POST` | Yêu cầu resource xử lý dữ liệu theo semantics riêng (tạo, hành động...) | Thường có, **không bắt buộc** | Không | Không được mặc định |
| `PUT` | Tạo/thay thế trạng thái resource đích bằng representation gửi lên | Thường có | Không | Có |
| `PATCH` | Áp dụng tập thay đổi một phần lên resource | Thường có | Không | **Không được mặc định** |
| `DELETE` | Yêu cầu xóa liên kết/trạng thái resource theo semantics dịch vụ | Có thể có, không có semantics chung bảo đảm | Không | Có |
| `OPTIONS` | Hỏi các tùy chọn giao tiếp với resource/server | Thường không cần | Có | Có |

**Safe** nghĩa là request được định nghĩa với mục đích **không yêu cầu làm thay đổi trạng thái** của server như một tác dụng nghiệp vụ chính. Truy cập GET vẫn có thể tạo log, đếm metrics hay quảng cáo theo thiết kế; safe không có nghĩa không có side effect kỹ thuật.

**Idempotent** nghĩa là nhiều request **giống nhau** có cùng *intended effect* trên server như một request. Nó **không** có nghĩa trả cùng một status/body:
- `PUT /settings/theme` gửi cùng một representation hai lần có thể để lại cùng trạng thái cuối.
- `DELETE /items/42` lần đầu có thể trả `204`, lần sau `404`; cả hai vẫn phù hợp với ý nghĩa idempotent nếu resource đã bị xóa và không có hành động phụ gây thay đổi khác.
- `POST /orders` gửi lại hai lần có thể tạo hai đơn hàng. Nếu dịch vụ muốn retry an toàn, cần cơ chế như **idempotency key** và lưu trạng thái giao dịch, không suy diễn từ tên POST.

### Method không tự quyết định route thành công

Request `GET /users/42` có method GET và URI đích, nhưng server có thể trả `200`, `401`, `403`, `404`, `429` hoặc `500` tùy trạng thái thật. Không có quy tắc “GET luôn 200, POST luôn 201”.

Cần tách **semantics chuẩn** và **contract API**:
- Chuẩn HTTP quy định ý nghĩa nền tảng của method, status, field.
- API định nghĩa tài nguyên, request/response schema, quyền truy cập và quy tắc nghiệp vụ.
- `PATCH` cần format patch và xử lý xung đột rõ ràng; không phải mọi server đều hỗ trợ.

**Khi method không được resource hỗ trợ**, dùng `405 Method Not Allowed` với `Allow` liệt kê method được hỗ trợ theo contract. `501 Not Implemented` khác: server không nhận biết/hỗ trợ chức năng cần thiết để thực hiện method đó ở mức máy chủ.

## 3. URI đích: scheme, authority, path, query và fragment

Một URI có thể phân tách:

~~~text
https://api.example.org:8443/v1/notes/42?view=full&lang=vi#details
└─scheme─┘ └──authority────┘└─path─────┘└─query──────────┘└fragment┘
~~~

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Scheme | `https` | Chỉ phương thức truy cập/giao thức bao ngoài, thường HTTPS = HTTP qua TLS |
| Authority | `api.example.org:8443` | Host và port đích (port có thể được suy từ scheme) |
| Path | `/v1/notes/42` | Đường đến resource được API định nghĩa |
| Query | `view=full&lang=vi` | Tham số bổ sung cho request target theo quy ước ứng dụng |
| Fragment | `details` | Chỉ vị trí/đoạn trong resource, **không được gửi trong HTTP request target** |

**Fragment** được xử lý phía client/user agent, không thuộc URI đích gửi trong HTTP request. Nếu Java `URI` có `#details`, đừng mong `HttpServer` nhìn thấy `#details` trong `getRequestURI()`.

### Những dạng request-target của HTTP/1.1

| Dạng | Ví dụ | Trường hợp |
|---|---|---|
| **origin-form** | `GET /v1/notes?tag=java HTTP/1.1` | Phổ biến khi client gửi request tới origin server |
| **absolute-form** | `GET http://example.org/v1/notes HTTP/1.1` | Thường dùng cho request tới HTTP forward proxy |
| **authority-form** | `CONNECT example.org:443 HTTP/1.1` | Dùng với CONNECT để yêu cầu lập đường hầm |
| **asterisk-form** | `OPTIONS * HTTP/1.1` | OPTIONS dành cho server nói chung |

Trong origin-form, scheme/host không xuất hiện trực tiếp trong request-line nhưng **Host** field cho biết authority của request; HTTP/1.1 client bắt buộc gửi `Host` theo chuẩn. Với HTTP/2/HTTP/3, ý nghĩa method/scheme/path/authority được biểu diễn chủ yếu qua các pseudo-header như `:method`, `:scheme`, `:authority`, `:path` (tùy loại request), **không** phải request-line text.

### Query không phải body

`GET /search?q=java&limit=5` gửi tham số ở **query** của target URI; `POST /search` có thể gửi JSON ở **body**. Cả hai có thể diễn đạt ý nghĩa tương tự nếu API thiết kế như vậy, nhưng ở mức giao thức chúng hoàn toàn khác:
- Query là một phần của URI target; có thể xuất hiện trong browser history, reverse-proxy logs và analytics.
- Body là dữ liệu trong message content và có Content-Type/Content-Encoding riêng.
- Query parameters **không có một parser chung bắt buộc của HTTP core**: quy ước `&`, `=`, tên trùng và `+` là thỏa thuận ở mức URL/form/application.
- Không đặt access token, password hoặc dữ liệu cá nhân nhạy cảm trong URI/query nếu có thể tránh; HTTPS bảo vệ trên đường mạng nhưng logs/history vẫn có thể lưu URI.

### Percent-encoding và raw/decoded

URI dùng percent-encoding để biểu diễn byte, ví dụ dấu cách `%20`, ký tự `/` có thể là dữ liệu segment khi được encode `%2F`. Java `URI` cung cấp cặp raw/decoded:

~~~java
URI uri = URI.create("https://example.org/a%2Fb?q=hello%20world");
System.out.println(uri.getRawPath()); // /a%2Fb
System.out.println(uri.getPath());    // /a/b
System.out.println(uri.getRawQuery()); // q=hello%20world
System.out.println(uri.getQuery());    // q=hello world
~~~

Đây là **snippet**, cần import `java.net.URI`. Đừng decode nhiều lần hoặc kiểm tra quyền trên raw path rồi route bằng decoded path khác, vì `%2F` có thể làm thay đổi cách phân đoạn và gây bypass security. Với form query, `+` thường mang nghĩa dấu cách **khi dùng application/x-www-form-urlencoded**; trong URI path và query nói chung không được tự ý thay mọi dấu `+` thành space.

## 4. Header: metadata của request/response

Header field trong HTTP/1.1 được trình bày bằng dòng `Field-Name: field-value`:

~~~http
Accept: application/json
Content-Type: application/json; charset=utf-8
Authorization: Bearer <redacted>
Cache-Control: no-store
~~~

Ví dụ trên dùng ký hiệu `<redacted>` chỉ giá trị đã ẩn để minh họa **không ghi token thật trong bài hoặc log**.

**Tên header không phân biệt chữ hoa/thường**: `Content-Type` và `content-type` chỉ cùng field name. Giá trị header lại có cú pháp/semantics tùy field; không phải mọi giá trị đều không phân biệt hoa/thường.

### Các header nên nắm

| Header | Request hay response? | Vai trò |
|---|---|---|
| `Host` | Request HTTP/1.1 | Host/authority mà client định truy cập |
| `Accept` | Request | Loại media type của representation mà client muốn nhận |
| `Content-Type` | Cả hai | Loại media của **body/representation được gửi trong message hiện tại** |
| `Content-Length` | Cả hai khi hợp lệ | Số octets liên quan message content theo quy tắc HTTP framing |
| `Content-Encoding` | Cả hai | Mã hóa representation như `gzip`, không phải charset |
| `Authorization` | Request | Thông tin xác thực client gửi cho server; cần bảo vệ khỏi log/lộ |
| `WWW-Authenticate` | Response, nhất là `401` | Cung cấp authentication challenge |
| `Cookie` / `Set-Cookie` | Request / Response | Session/cookie state ở tầng HTTP; thường có thông tin nhạy cảm |
| `Location` | Response, thường `201` hoặc 3xx | URI resource mới hoặc redirect target theo status |
| `Cache-Control` | Cả hai | Chỉ thị caching, revalidation và/hoặc privacy cache |
| `ETag` / `If-None-Match` | Response / Request | Entity tag và conditional requests; có thể dẫn tới `304` |
| `If-Match` | Request | Điều kiện cập nhật, thường dùng tránh lost update |
| `Allow` | Response, đặc biệt `405` | Liệt kê methods được target resource hỗ trợ |
| `Retry-After` | Response trong một số trường hợp | Gợi ý thời gian chờ trước khi thử lại |
| `Vary` | Response | Những request header ảnh hưởng lựa chọn representation khi cache |

**`Accept` vs `Content-Type`:** request `Accept: application/json` nói client **muốn nhận JSON**. Request `Content-Type: application/json` nói bytes **client đang gửi** là JSON. Response `Content-Type: application/json` nói bytes **server trả** là JSON. Không tráo hai ý nghĩa.

**`Content-Type` vs `Content-Encoding`:** `application/json; charset=utf-8` mô tả media type và charset; `Content-Encoding: gzip` nói representation được nén gzip. Nếu nén, bên nhận cần xử lý content-coding trước khi diễn giải representation theo media type và charset.

**Header field lặp:** một số field hỗ trợ gộp danh sách, nhưng **không phải tất cả**. Đặc biệt, `Set-Cookie` không được gộp tùy tiện thành một dòng comma-separated; `Content-Length` lặp hoặc mâu thuẫn có thể làm request/response không hợp lệ và nguy hiểm. Đừng tự parse HTTP header bằng split các dấu phẩy/dấu hai chấm mà không tuân theo grammar của field.

**Giới hạn kích thước:** header dài quá mức làm tăng memory/CPU và có thể bị server/proxy từ chối. Hệ thống thật nên đặt tổng byte header, số field, độ dài mỗi field và xử lý newline không hợp lệ để tránh header injection/smuggling.

## 5. Body: bytes của nội dung, không phải string mặc định

Một HTTP message **có thể có hoặc không có content/body**. Khi có body, nó được diễn giải dựa trên method/status và metadata:
- JSON: `Content-Type: application/json`.
- Văn bản: `Content-Type: text/plain; charset=utf-8`.
- Form: `application/x-www-form-urlencoded`.
- Multipart: `multipart/form-data; boundary=...`.
- Binary: `application/octet-stream` hoặc media type cụ thể.

Không suy ra request `POST` bắt buộc có JSON body, hoặc request `GET` bắt buộc có body. **GET request content không có semantics chung được chuẩn HTTP xác định** và không nên dùng để mang tham số nghiệp vụ quan trọng; nhiều proxy/client không xử lý nhất quán.

### Độ dài byte, không phải số ký tự

Trong HTTP/1.1, khi một body có độ dài biết trước và `Content-Length` hợp lệ, giá trị phải theo **số byte**, không phải số ký tự Java:

~~~java
String json = "{\"title\":\"Tiếng Việt\"}";
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
int length = bytes.length; // Số byte UTF-8, không dùng json.length().
~~~

Đây là snippet Java, cần import `java.nio.charset.StandardCharsets`. Các ký tự `ế`/`ệ` thường chiếm nhiều byte UTF-8 nhưng có thể chiếm một đơn vị UTF-16; emoji có thể chiếm hai đơn vị UTF-16 và bốn byte UTF-8.

### Framing trong HTTP/1.1

HTTP/1.1 cần biết **nơi message content kết thúc** để có thể tiếp tục đọc message kế trên cùng TCP connection. Những cơ chế quan trọng:
- **`Content-Length` hợp lệ** mô tả số octet content, với các quy tắc riêng cho một số method/status.
- **`Transfer-Encoding: chunked`** trong HTTP/1.1 sử dụng các chunk có size ở dạng hexadecimal, kết thúc bằng chunk cuối size 0 và có thể có trailer fields. Kích thước chunk là framing wire, **không** là một phần JSON body sau khi decode framing.
- Một số trường hợp legacy có framing bằng đóng kết nối; nhưng không nên dựa vào EOF khi muốn persistent connection.
- **HTTP/2 và HTTP/3** dùng frame/stream semantics để xác định nội dung, **không** dùng chuỗi chunked `Transfer-Encoding` như HTTP/1.1. Không tự thêm `Transfer-Encoding: chunked` vào HTTP/2 request.

**Tránh request smuggling:** nếu reverse proxy và backend không nhất quán về `Content-Length`/`Transfer-Encoding`, chúng có thể phân đoạn các request khác nhau trên cùng byte stream. Luôn dùng HTTP parser/stack đáng tin, cấu hình proxy/server cùng chính sách và **từ chối framing mơ hồ hoặc sai**. Đừng tự viết HTTP parser production bằng vài lời gọi `BufferedReader.readLine()`.

### Những trường hợp không truyền response body

- `HEAD`: server trả các header phản ánh GET nhưng **không gửi response content**.
- Status `1xx`, `204 No Content` và `304 Not Modified`: không chứa response content theo quy tắc HTTP.
- Thành công `CONNECT` chuyển thành tunnel sau response phù hợp, có semantics đặc biệt.

Dù `204` không có body, application code vẫn có thể muốn đặt `ETag` hoặc cache metadata hợp lệ. `304` dùng conditional cache revalidation, không đồng nghĩa một JSON body chứa mã “not modified”.

Body của **error response** thường có thể chứa thông tin lỗi hữu ích, nhưng không nên để lộ stack trace, secret, password, dữ liệu nội bộ cho client công khai.

## 6. Status code: kết quả HTTP chứ không phải nội dung ứng dụng

Mỗi response có **status code ba chữ số**. Chữ số đầu mô tả nhóm:

| Nhóm | Tên | Ý nghĩa |
|---|---|---|
| `1xx` | Informational | Thông tin tạm thời trong quá trình xử lý; ví dụ `100 Continue`, `101 Switching Protocols` |
| `2xx` | Successful | Request được xử lý thành công theo semantics status; ví dụ `200`, `201`, `202`, `204` |
| `3xx` | Redirection | Cần dùng/kiểm tra URI khác hoặc cache validation; ví dụ `301`, `302`, `303`, `304`, `307`, `308` |
| `4xx` | Client Error | Không thể xử lý request do điều kiện ở phía request/client theo định nghĩa status; ví dụ `400`, `401`, `403`, `404`, `405`, `409`, `415`, `429` |
| `5xx` | Server Error | Server gặp lỗi/không thể đáp ứng; ví dụ `500`, `502`, `503`, `504` |

Một số status thực dụng:

| Status | Tên | Dùng khi nào / lưu ý |
|---|---|---|
| `200 OK` | Thành công | Response có representation phù hợp với method; GET thường trả body |
| `201 Created` | Đã tạo resource | Có thể dùng `Location` trỏ tới resource được tạo |
| `202 Accepted` | Chấp nhận xử lý | Công việc có thể chưa hoàn thành; cần contract theo dõi tiến trình/kết quả |
| `204 No Content` | Thành công không có content | Không gửi response body |
| `301 Moved Permanently` | Chuyển vĩnh viễn | Chỉ hướng target mới; client/cache có thể xử lý redirect theo policy |
| `302 Found` | Chuyển tạm thời | Lịch sử client có khác biệt chuyển POST sang GET; muốn bảo toàn method/body dùng `307`/`308` |
| `303 See Other` | Xem tài nguyên khác | Thường redirect sang GET để xem kết quả của POST |
| `304 Not Modified` | Không cần gửi lại representation | Conditional cache validation; không có body |
| `307 Temporary Redirect` | Chuyển tạm, **giữ method/body** | Tránh đổi POST thành GET |
| `308 Permanent Redirect` | Chuyển vĩnh viễn, **giữ method/body** | Dùng khi cần bảo toàn semantics method |
| `400 Bad Request` | Request sai | Syntax/parameter/framing không hợp lệ theo xử lý của server |
| `401 Unauthorized` | Chưa có thông tin xác thực hợp lệ | Tên hơi gây nhầm; thực tế là **authentication required/failed**, thường đi kèm `WWW-Authenticate` |
| `403 Forbidden` | Server từ chối | Có thể đã biết danh tính nhưng **không cho phép**, hoặc từ chối theo chính sách |
| `404 Not Found` | Không thấy resource | Có thể dùng cả khi server không muốn tiết lộ resource có tồn tại |
| `405 Method Not Allowed` | Method không được hỗ trợ cho resource | Response cần `Allow` mô tả methods được phép |
| `409 Conflict` | Xung đột trạng thái | Ví dụ version/state xung đột, cần giải quyết trước khi retry |
| `412 Precondition Failed` | Điều kiện request sai | Ví dụ `If-Match` không khớp, hỗ trợ optimistic concurrency |
| `415 Unsupported Media Type` | Không hỗ trợ định dạng request content | Ví dụ API nhận JSON nhưng nhận content type khác |
| `422 Unprocessable Content` | Cú pháp content hiểu được nhưng không xử lý theo instructions | Thường dùng validation nghiệp vụ theo contract |
| `429 Too Many Requests` | Rate limit | Có thể gửi `Retry-After` để hướng dẫn client |
| `500 Internal Server Error` | Lỗi server không phân loại chi tiết | Không trả stack trace nhạy cảm |
| `502 Bad Gateway` | Gateway/proxy nhận upstream response không hợp lệ | Phân biệt với server ứng dụng xử lý request |
| `503 Service Unavailable` | Server tạm không sẵn sàng/quá tải | Có thể kèm `Retry-After` |
| `504 Gateway Timeout` | Gateway/proxy đợi upstream quá lâu | Không giống client read timeout ở mọi trường hợp |

**Status vs app business code:** body `{"error":"OUT_OF_STOCK"}` có thể mô tả lỗi nghiệp vụ, nhưng HTTP status vẫn cần đúng semantics. Không trả `200 OK` cho mọi lỗi và hy vọng client luôn đọc body để đoán thành công.

**Status không phải chỉ số bảo mật:** `401` và `403` đều cần xử lý login/permission đúng; response `404` không thay thế permission checks ở backend. `5xx` có thể do server, upstream hoặc hạ tầng tùy status và kiến trúc.

## 7. Đọc một request/response hoàn chỉnh

Ví dụ một giao dịch tạo ghi chú:

~~~http
POST /notes HTTP/1.1
Host: api.example.org
Accept: application/json
Content-Type: application/json
Content-Length: 16

{"title":"Java"}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /notes/42
Content-Length: 16

{"created":true}
~~~

Để tự kiểm:
- Request method `POST` là lời yêu cầu xử lý/tạo, URI target là `/notes`.
- `Host` cho biết authority; `Accept` và `Content-Type` làm các việc khác nhau.
- Body request `{"title":"Java"}` dài **16 byte** ASCII.
- Response `201` nói tài nguyên mới được tạo; `Location: /notes/42` chỉ vị trí tài nguyên theo contract.
- Body response `{"created":true}` cũng dài **16 byte** ASCII.
- Nếu client gửi `Content-Type: text/plain` nhưng API chỉ nhận JSON, response `415` có thể đúng hơn là parser cố hiểu nó như JSON.
- Nếu URI `/notes/missing` không có resource, `404` phù hợp; nếu `PATCH` không được route hỗ trợ, `405` cùng `Allow` hữu ích.

Các ví dụ wire trên mô tả HTTP/1.1 text. Trong hoạt động thật, header order/capitalization, chunked/Content-Length và connection management do HTTP library chọn có thể khác nhưng semantics giữ nguyên.

## 8. Java 17+ demo: HTTP method, target URI, header, status và body

Để kiểm tra mà không phụ thuộc Internet, dùng `com.sun.net.httpserver.HttpServer` (module `jdk.httpserver` thuộc JDK tiêu chuẩn) cho **HTTP server loopback**, và `java.net.http.HttpClient` cho client. Code ép client HTTP/1.1 để liên hệ với request/response text trong bài.

Demo có:
- `GET /notes?tag=java` trả `200` và JSON body.
- `POST /notes` gửi JSON body, trả `201`, header `Location: /notes/42` và JSON response.
- Route khác trả `404`; query sai trả `400`; `Content-Type` sai trả `415`; body quá giới hạn của demo trả `413`; method khác trả `405` và `Allow`.
- Chỉ in những phần response quan trọng, tránh phụ thuộc thứ tự/capitalization các header do HTTP stack tự tạo.

Lưu trọn vẹn thành file **`HttpPartsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpPartsDemo {
    private static void reply(HttpExchange ex, int status,
                              String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type",
                                    "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void handle(HttpExchange ex) throws IOException {
        try {
            String method = ex.getRequestMethod();
            String path = ex.getRequestURI().getRawPath();

            if (!"/notes".equals(path)) {
                reply(ex, 404, "{\"error\":\"not found\"}");
                return;
            }
            if ("GET".equals(method)) {
                if (!"tag=java".equals(ex.getRequestURI().getRawQuery())) {
                    reply(ex, 400, "{\"error\":\"invalid query\"}");
                    return;
                }
                reply(ex, 200, "{\"items\":[\"java\"]}");
            } else if ("POST".equals(method)) {
                String type = ex.getRequestHeaders().getFirst("Content-Type");
                if (type == null || !type.equalsIgnoreCase("application/json")) {
                    reply(ex, 415, "{\"error\":\"unsupported type\"}");
                    return;
                }
                byte[] body = ex.getRequestBody().readNBytes(513);
                if (body.length > 512) {
                    reply(ex, 413, "{\"error\":\"too large\"}");
                    return;
                }
                // Demo nhận bytes, không parse/validate JSON.
                ex.getResponseHeaders().set("Location", "/notes/42");
                reply(ex, 201, "{\"created\":true}");
            } else {
                ex.getResponseHeaders().set("Allow", "GET, POST");
                reply(ex, 405, "{\"error\":\"method not allowed\"}");
            }
        } finally {
            ex.close();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
            new InetSocketAddress(loopback, 0), 0);
        server.createContext("/", HttpPartsDemo::handle);
        server.start();
        try {
            int port = server.getAddress().getPort();
            URI base = URI.create("http://127.0.0.1:" + port);
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1).build();

            HttpRequest get = HttpRequest.newBuilder(
                    base.resolve("/notes?tag=java"))
                .header("Accept", "application/json")
                .GET().build();
            HttpResponse<String> getResponse = client.send(
                get, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            System.out.println("GET request: " + get.method()
                + " " + get.uri().getRawPath()
                + "?" + get.uri().getRawQuery());
            System.out.println("GET status: " + getResponse.statusCode());
            System.out.println("GET Content-Type: "
                + getResponse.headers().firstValue("Content-Type").orElse(""));
            System.out.println("GET body: " + getResponse.body());

            HttpRequest post = HttpRequest.newBuilder(
                    base.resolve("/notes"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                    "{\"title\":\"Java\"}", StandardCharsets.UTF_8))
                .build();
            HttpResponse<String> postResponse = client.send(
                post, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            System.out.println("POST request: " + post.method()
                + " " + post.uri().getRawPath());
            System.out.println("POST status: " + postResponse.statusCode());
            System.out.println("POST Location: "
                + postResponse.headers().firstValue("Location").orElse(""));
            System.out.println("POST body: " + postResponse.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Biên dịch, chạy và output

Trong thư mục chỉ chứa file Java demo:

~~~bash
javac -encoding UTF-8 HttpPartsDemo.java
java HttpPartsDemo
~~~

Stdout xác định đã được chạy thử bằng Java trên TCP loopback:

~~~text
GET request: GET /notes?tag=java
GET status: 200
GET Content-Type: application/json; charset=utf-8
GET body: {"items":["java"]}
POST request: POST /notes
POST status: 201
POST Location: /notes/42
POST body: {"created":true}
~~~

`HttpServer` mở cổng `0` trên `127.0.0.1`, tức hệ điều hành chọn cổng trống và máy khác không truy cập listener qua interface mạng công khai. `server.stop(0)` đóng listener ngay sau thử nghiệm. Trong custom runtime image có thể phải giữ module `jdk.httpserver`; JDK 17 tiêu chuẩn dùng được trực tiếp như các lệnh trên.

### Giải thích từng phần của chương trình

1. **Tạo HTTP listener:** `HttpServer.create(new InetSocketAddress(loopback, 0), 0)` bind cổng động; `createContext("/", ...)` chuyển request tới handler. Đây là HTTP library, **không** bắt bạn viết parser cho `GET ... HTTP/1.1` bằng tay.
2. **Method và URI target:** `ex.getRequestMethod()` trả method; `ex.getRequestURI().getRawPath()` là raw path. Query lấy bằng `getRawQuery()`, **không** tự lẫn vào path. Demo so sánh raw query nguyên văn `tag=java`, không phải parser query tổng quát.
3. **Header:** `getRequestHeaders().getFirst("Content-Type")` đọc header request. Client `.header("Accept", ...)` và `.header("Content-Type", ...)` có mục đích khác nhau; server `set("Content-Type",...)` cho response.
4. **Body request:** `getRequestBody().readNBytes(513)` đọc tối đa 513 byte để kiểm tra giới hạn minh họa **512 byte**; không decode từng fragment hay dùng `String.length()` để đo payload bytes. Demo **không parse/validate JSON**, nên không dùng nó làm JSON API production.
5. **Status response:** `sendResponseHeaders(status, bytes.length)` gửi code và cơ chế length theo API; với body không rỗng của demo, phía server gửi đúng số bytes và đóng response stream. Không tự thêm một `Content-Length` tùy tiện vào `HttpClient`: thư viện đảm nhận framing wire.
6. **`201 Created` và `Location`:** response POST có header `Location: /notes/42`; đây là ví dụ một tài nguyên mới, không chứng minh server đã lưu vào database. Demo chỉ tạo body tĩnh, chưa có persistence.
7. **`HttpClient`:** `HttpRequest` định nghĩa method/URI/header/body; `BodyPublishers.ofString` chuyển request body thành bytes UTF-8; `HttpResponse.BodyHandlers.ofString` giải mã response text.
8. **Đọc response:** `statusCode()` lấy status; `headers().firstValue(...)` lấy header; `body()` trả body. Cần kiểm tra status **trước** khi diễn giải body theo schema “thành công”.
9. **Resource cleanup:** server dừng trong `finally`. Ví dụ chạy một JVM tự tạo cả client và server, không phụ thuộc host public hay mạng ngoài.

**Giới hạn demo:** không có authentication/authorization, persistence, JSON schema validation, concurrency control, structured logging hay cơ chế rate limiting. Đưa vào production cần HTTP stack/framework có giới hạn request/header size, timeout, TLS, kiểm soát truy cập và xử lý lỗi. `HttpServer` chỉ phục vụ minh họa các thành phần giao thức.

## 9. HTTP/1.1 so với HTTP/2 và HTTP/3

**Semantics cốt lõi ổn định:** method, target URI, header fields, status và content đều tồn tại ở cả ba phiên bản. Điều thay đổi lớn là **message framing trên wire**.

| Tiêu chí | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Transport phổ biến | TCP | TCP với TLS trong triển khai web thông dụng | QUIC trên UDP |
| Bản tin trên wire | Start-line + text header + CRLF + body/framing | Binary frames/streams | QUIC streams + HTTP/3 frames |
| Method/status | Request-line/status-line text | Pseudo-headers `:method`, `:status` | Pseudo-headers với semantics tương ứng |
| Authority/path | Host và request-target | `:authority`, `:scheme`, `:path` | Tương tự ở layer HTTP/3 |
| Header compression | Không bắt buộc ở wire-format HTTP/1.1 | HPACK | QPACK |
| Multiplexing | Không có multiplexed streams theo mô hình HTTP/2 | Nhiều streams trên một TCP connection | Nhiều QUIC streams |
| Chunked transfer encoding | Có trong HTTP/1.1 | Không dùng `chunked` như message framing | Không dùng `chunked` như HTTP/1.1 |

Trong HTTP/2/3, **không** tìm literal `HTTP/1.1 200 OK` trên wire. Thay vào đó, frame chứa metadata/status như `:status: 200`. Header field names trong HTTP/2/3 được mã hóa/chuẩn hóa theo quy tắc version (thường lowercase trên wire). Điều này không làm HTTP request `POST` “khác nghĩa” về semantics ứng dụng.

Trong Java `HttpClient`, có thể yêu cầu phiên bản theo `.version(HttpClient.Version.HTTP_2)`, nhưng **phiên bản thực tế phụ thuộc negotiation/server**; kiểm tra `HttpResponse.version()`. Ví dụ bài cố tình chọn HTTP/1.1 vì `HttpServer` demo và cấu trúc text trực quan, không dùng ví dụ như chứng cứ HTTP/2/3 đã được thử nghiệm.

## 10. Lỗi thường gặp và rủi ro bảo mật

| Sai lầm | Vì sao sai? | Hướng sửa |
|---|---|---|
| “GET luôn trả `200`.” | Status phản ánh kết quả thực tế | Xử lý cả 2xx/3xx/4xx/5xx |
| “POST luôn có JSON body.” | Method không định nghĩa format content | Kiểm tra `Content-Type`, contract và độ dài |
| “`Accept` mô tả JSON client gửi.” | `Accept` mô tả mong muốn **nhận** | `Content-Type` mới mô tả content đang gửi |
| “Query cũng là body.” | Query nằm trong target URI, body nằm sau headers | Lấy `getRawQuery()` và request body riêng |
| “`#fragment` được gửi cho server.” | Fragment client-side, không nằm trong request-target | Không dùng fragment làm tham số server |
| “Hostname trong `Host` luôn đáng tin.” | Client có thể sửa Host; nhiều proxy có thể thay đổi | Validate allowed hosts, trusted forwarding headers |
| “`String.length()` là `Content-Length`.” | UTF-8 byte length có thể lớn hơn | Đếm encoded bytes, để HTTP library framing |
| “Cứ `readLine` đến EOF sẽ parse HTTP.” | Body binary, chunked, streaming, pipelining phức tạp | Dùng thư viện HTTP đúng chuẩn |
| “`Transfer-Encoding` và `Content-Length` luôn dùng chung vô hại.” | Framing mơ hồ giữa proxy/backend gây request smuggling | Dùng parser đáng tin, reject HTTP/1.1 framing mâu thuẫn |
| “Header name phân biệt hoa/thường.” | Field names case-insensitive | Dùng API header lookup thay vì so chuỗi tay |
| “Mọi repeated header gộp bằng dấu phẩy được.” | `Set-Cookie` và một số field có ngoại lệ | Theo grammar của từng field |
| “`204` chứa JSON body bình thường.” | `204` không mang response content | Chọn status có content khi cần body |
| “`401` nghĩa là người dùng đã đăng nhập nhưng không có quyền.” | `401` liên quan **authentication**; `403` thường là từ chối | Phân biệt authn/authz |
| “`404` luôn chứng minh resource không tồn tại.” | Có thể che resource theo policy | Không dựa 404 để suy toàn bộ state |
| “`200` cùng body `error` nghĩa là status vẫn đúng.” | HTTP status phải phản ánh semantics | Dùng 4xx/5xx phù hợp, body giải thích |
| “Có HTTPS thì query token không thể lộ.” | URI có thể được ghi ở logs/history/analytics | Tránh secret trong URL; redaction |
| “`Content-Type: application/json` nghĩa body JSON chắc chắn hợp lệ.” | Header là khai báo, không tự validate | JSON parser + schema validation |
| “Retry POST vô hạn là an toàn.” | POST không mặc định idempotent | Idempotency key và retry policy |
| “Đổi `301`/`302` tương đương `307`/`308` cho POST.” | Redirect method/body semantics khác | Chọn status đúng và test client |
| “Không có `Content-Length` nghĩa là không có body.” | Có chunked hoặc framing khác | Dựa vào HTTP parser/semantics |
| “`HttpResponse.body()` luôn là JSON.” | Content có thể là error HTML, text, binary | Kiểm tra status và Content-Type trước parse |

### An toàn URI và header

- Không ghép nguyên chuỗi input người dùng vào `URI.create("https://host/" + userInput)` mà không encode/validate. Ký tự `?`, `#`, `/` hoặc percent escapes có thể đổi semantics path/query.
- Nếu server/client tải URL do người dùng cung cấp, kiểm tra nguy cơ **SSRF**: URL có thể trỏ tới loopback, metadata service, private networks hoặc chuyển hướng sang địa chỉ nội bộ. Cần allowlist/resolve policy và kiểm tra redirect theo kiến trúc.
- Không dùng dữ liệu chưa tin cậy từ `Host`, `Forwarded` hoặc `X-Forwarded-Host` để phát sinh redirect/callback URL nhạy cảm trừ khi đã xác thực proxy nguồn và chính sách host.
- Không log nguyên văn `Authorization`, `Cookie`, `Set-Cookie` hoặc query chứa secret; dùng redaction và kiểm soát retention.
- Không decode path nhiều lần hoặc áp authorization trước/sau decode không nhất quán. `%2F`, `%2E` và normalization có thể gây route/path traversal nếu các tầng xử lý khác nhau.
- Response body nhận từ mạng là dữ liệu chưa tin cậy; `Content-Type` không chứng minh parser phải tin toàn bộ payload.

## 11. Checklist khi thiết kế một HTTP endpoint

Trước khi phát hành endpoint, hãy trả lời lần lượt:

1. **Method:** GET để đọc, POST để xử lý/tạo, PUT để replace, PATCH để partial update, DELETE để xóa có phù hợp? Request nào được retry an toàn?
2. **URI:** resource có path rõ, query có semantics rõ, percent-encoding thống nhất? Có bỏ secret khỏi query và fragment phía server?
3. **Request headers:** `Content-Type`, `Accept`, authorization, conditional/caching headers được xử lý đúng? Header lạ/sai có bị bỏ qua/từ chối nhất quán?
4. **Request body:** cần hay không; media type nào; charset; giới hạn byte; streaming và JSON/schema validation? Có xử lý body không đầy đủ, sai length, timeout?
5. **Response status:** trả `200`/`201`/`204` cho success, `400`/`401`/`403`/`404`/`405`/`409`/`415`/`429` cho lỗi tương ứng, `5xx` cho lỗi server?
6. **Response headers:** `Content-Type`, `Location`, `Allow`, `Cache-Control`, `ETag`/`Vary` hợp lý? Có truyền nội dung nhạy cảm vào cache public?
7. **Response body:** định dạng thành công/lỗi thống nhất, không lộ secret/stack trace; có đúng độ dài byte và không phát body ở status/method bị cấm?
8. **Transport:** timeout, TLS, kích thước header/body, connection limits, parser/proxy đúng chuẩn để chống request smuggling?
9. **Observability:** metrics method/status/latency/bytes theo route, log được redaction, không log raw token/PII?
10. **Kiểm thử:** method sai, query percent-encoded, request size lớn, missing Content-Type, body invalid, expired authentication, concurrent update, conditional requests, redirect và retry?

Chỉ dùng status code để mô tả outcome; không biến `status=200` thành “mọi chuyện đều đúng” khi nội dung ứng dụng chưa được kiểm tra.

## 12. Bài tập thực hành

1. Trong request `POST /users?notify=true` với header `Content-Type: application/json`, phần nào là method, URI target, header và body? `notify=true` nằm ở đâu?
2. Vì sao `GET /search?q=java#results` không khiến server nhận `#results`?
3. Phân biệt ý nghĩa `Accept: application/json` với `Content-Type: application/json` khi cùng xuất hiện trong request.
4. Một client gửi `{"title":"Tiếng Việt"}`. Vì sao `String.length()` không thể được dùng làm `Content-Length`?
5. Nêu ví dụ một request idempotent nhưng hai lần gửi có thể trả status khác nhau.
6. Một `POST /notes` thành công tạo resource `/notes/42`. Chọn status và header nào phù hợp? Body có bắt buộc không?
7. Server nhận `PATCH` nhưng resource chỉ cho `GET` và `POST`. Status và header nào nên dùng?
8. Một API trả `401`, API khác trả `403`. Chúng thường khác nhau ở điểm nào?
9. Một GET có `If-None-Match` khớp với `ETag` hiện tại. Status nào cho phép cache dùng lại representation mà không gửi body?
10. Khi server trả `204`, có được gửi JSON body mô tả “success” không?
11. Tại sao `Transfer-Encoding: chunked` là framing phù hợp với HTTP/1.1 nhưng không phải framing của HTTP/2?
12. Vì sao reverse proxy và backend parse `Content-Length`/`Transfer-Encoding` mâu thuẫn có thể tạo lỗ hổng request smuggling?
13. Trong code Java demo, `getRequestURI().getRawPath()` và `getRawQuery()` trả gì với GET `/notes?tag=java`?
14. Thử sửa request của demo thành `GET /notes?tag=python`. Theo handler, status/body sẽ là gì? Đây có phải lỗi TCP không?
15. Thử sửa POST `Content-Type` thành `text/plain`. Status mong đợi là gì và vì sao?
16. HTTP/2 không có dòng `HTTP/1.1 201 Created` dưới dạng wire text. Vậy thông tin status nằm ở đâu?

**Đáp án cốt lõi:** (1) method POST, target `/users?notify=true`, JSON header mô tả body; (2) fragment phía client; (3) Accept là muốn nhận, Content-Type là đang gửi; (4) `Content-Length` đếm byte sau encoding; (5) DELETE lần đầu 204, lần sau 404 mà state không đổi; (6) `201` và có thể `Location`; (7) `405` với `Allow`; (8) xác thực vs từ chối quyền; (9) `304`; (10) không; (11) HTTP/2 frame-based; (12) hai tầng có thể hiểu lệch ranh giới request; (13) `/notes` và `tag=java`; (14) `400` + JSON invalid query, không phải lỗi TCP; (15) `415` vì server chấp nhận JSON trong demo; (16) pseudo-header `:status`.

## 13. Tổng kết

- **Method** quy định *ý định thao tác*; phân biệt safe và idempotent, không áp một status cố định cho mọi method.
- **URI đích** xác định tài nguyên, path/query là dữ liệu khác body; fragment không được gửi tới server và percent-encoding phải được xử lý nhất quán.
- **Header** mang metadata/điều khiển; `Accept` là loại muốn nhận, `Content-Type` là loại đang gửi, `Content-Length` nói về **byte** chứ không phải `String.length()`.
- **Status code** là semantics của kết quả HTTP: 2xx thành công, 3xx chuyển hướng/cache, 4xx lỗi ở phía request, 5xx lỗi server/upstream. Body có thể giải thích chi tiết nhưng không thay status.
- **Body** là representation/content, có thể là JSON/text/binary và không luôn tồn tại; HTTP parser phải nắm đúng framing, đặc biệt với HTTP/1.1.
- **Java 17:** `HttpRequest` tạo method/URI/headers/body, `HttpResponse` trả status/headers/body; dùng HTTP library thay vì tự parse bytes HTTP.
- **An toàn:** giới hạn byte, validate URI/host/headers, kiểm tra auth, không log secret, không dùng framing mơ hồ giữa proxy/backend.

### Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics: methods, request target, field values, status codes](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9112 — HTTP/1.1: message syntax, framing, content length and chunked](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html)
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Oracle Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
