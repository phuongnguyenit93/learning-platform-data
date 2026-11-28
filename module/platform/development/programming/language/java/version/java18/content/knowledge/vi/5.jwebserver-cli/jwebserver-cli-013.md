# GET và HEAD: kiểm tra status, header và sự khác biệt về response body

## 1. GET và HEAD dùng để làm gì?

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ vẫn được hỗ trợ trên JDK hiện đại, bao gồm JDK 27.

Simple Web Server hỗ trợ hai HTTP method:

- **GET:** yêu cầu tài nguyên và nhận nội dung tài nguyên trong response body.
- **HEAD:** yêu cầu metadata của cùng tài nguyên, nhận response headers nhưng không nhận response body.

Cả hai method đều có tính chất idempotent. Với cùng URL và cùng điều kiện request, HEAD được xử lý theo cùng cách chọn tài nguyên như GET. Điểm khác biệt chính là HEAD không gửi phần nội dung response.

Ví dụ, với một tệp HTML:

```http
GET /index.html HTTP/1.1
Host: 127.0.0.1:8080
```

server trả status, headers và nội dung HTML.

Request HEAD:

```http
HEAD /index.html HTTP/1.1
Host: 127.0.0.1:8080
```

server trả status và headers tương ứng, nhưng không gửi HTML body.

HEAD hữu ích khi muốn kiểm tra một URL có tồn tại hay không, kiểu nội dung, kích thước biểu diễn hoặc thông tin phản hồi mà không cần tải nội dung tệp về client.

> **Phạm vi:** Simple Web Server chỉ phục vụ tài nguyên tĩnh qua HTTP/1.1. Công cụ không hỗ trợ HTTP/2, HTTPS, xác thực người dùng hoặc xử lý nghiệp vụ web động; phù hợp cho phát triển, thử nghiệm và gỡ lỗi, không dùng làm máy chủ production.

## 2. Hiểu response gồm status line, headers và body

Một HTTP response thường có ba phần:

```text
HTTP/1.1 200 OK                 <- Status line
Content-Type: text/html        <- Response headers
Content-Length: 148

<!doctype html>                <- Response body
<html>...</html>
```

| Thành phần | Ý nghĩa |
| --- | --- |
| Status line | Phiên bản HTTP, mã trạng thái và cụm mô tả trạng thái. |
| Response headers | Metadata về response và tài nguyên được chọn. |
| Response body | Nội dung biểu diễn được gửi về client, nếu response có body. |

Ví dụ, khi GET một tệp HTML thành công:

- Status có thể là `200 OK`.
- `Content-Type` thường cho biết `text/html`.
- `Content-Length`, nếu được gửi, cho biết số byte của nội dung.
- Response body chứa nội dung HTML.

Khi HEAD cùng URL:

- Status thường giống với GET cho cùng tài nguyên và cùng điều kiện request.
- Các header mô tả biểu diễn được gửi tương ứng với GET.
- Không có response body.

**Không nhầm response headers với request headers.** Request headers do client gửi lên, ví dụ `Host`, `User-Agent` và `Accept`. Response headers do server gửi về, ví dụ `Content-Type`, `Content-Length` và `Location`.

## 3. GET: lấy nội dung tài nguyên

Giả sử thư mục phục vụ có cấu trúc:

```text
public/
├── index.html
├── about.html
├── assets/
│   └── app.css
└── data/
    └── sample.json
```

Khởi động server từ thư mục cha:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Gửi GET tới trang chủ:

```sh
curl -i http://127.0.0.1:8080/
```

Tùy chọn `-i` yêu cầu curl hiển thị response headers cùng response body. Kết quả thành công có dạng minh họa:

```http
HTTP/1.1 200 OK
Date: Fri, 27 Nov 2026 05:00:00 GMT
Content-type: text/html
Content-length: 148

<!doctype html>
<html lang="vi">
...
</html>
```

Các giá trị ngày giờ, kích thước và header thực tế phụ thuộc tệp, JDK và môi trường. Đoạn trên chỉ minh họa cấu trúc response.

GET thực hiện hai việc có thể quan sát:

1. Server tìm tài nguyên tương ứng với URI path trong document root.
2. Nếu tài nguyên được phục vụ, server gửi nội dung biểu diễn trong response body.

Một số request ví dụ:

```sh
# Trang HTML:
curl -i http://127.0.0.1:8080/about.html

# Tệp CSS:
curl -i http://127.0.0.1:8080/assets/app.css

# Tệp JSON:
curl -i http://127.0.0.1:8080/data/sample.json
```

GET thích hợp khi cần xem nội dung thực tế, kiểm tra encoding, đọc JSON, xác minh HTML hoặc tải tệp.

## 4. HEAD: chỉ lấy metadata, không lấy response body

### 4.1. Gửi HEAD bằng curl

Tùy chọn `-I` (hoặc `--head`) của curl gửi request HEAD:

```sh
curl -I http://127.0.0.1:8080/about.html
```

Response minh họa:

```http
HTTP/1.1 200 OK
Date: Fri, 27 Nov 2026 05:00:00 GMT
Content-type: text/html
Content-length: 148
```

Bạn nhận status và headers, nhưng không nhận nội dung HTML phía sau headers.

Đây là cách nhanh để kiểm tra metadata của tài nguyên. HEAD không tải phần biểu diễn body về client như GET.

### 4.2. HEAD không phải GET bị ẩn output ở terminal

Hai thao tác sau khác nhau:

```sh
# HEAD: server nhận request method HEAD và không gửi body:
curl -I http://127.0.0.1:8080/about.html

# GET: server nhận GET; curl bỏ body khỏi output terminal:
curl -sS -D - -o /dev/null http://127.0.0.1:8080/about.html
```

Lệnh thứ hai vẫn gửi GET và server vẫn tạo response body. Tùy chọn `-o /dev/null` chỉ yêu cầu curl bỏ nội dung nhận được tại phía client; `-D -` in response headers ra standard output.

Trên Windows PowerShell, có thể dùng:

```powershell
# HEAD:
curl.exe -I http://127.0.0.1:8080/about.html

# GET, in headers và bỏ body:
curl.exe -sS -D - -o NUL http://127.0.0.1:8080/about.html
```

Trong Windows PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest`. Gọi rõ `curl.exe` để dùng curl thực.

### 4.3. HEAD không có nghĩa là server không xử lý tài nguyên

Server vẫn phải xác định tài nguyên và tạo response phù hợp với request. Với một tệp tĩnh, server có thể lấy metadata cần thiết như kiểu nội dung và kích thước. Khác biệt giao thức là client không nhận response body.

Không nên giả định HEAD luôn rẻ hơn GET trong mọi implementation hoặc mọi loại tài nguyên. Với Simple Web Server, mục đích trực tiếp của HEAD là lấy headers mà không truyền nội dung tệp về client.

## 5. So sánh GET và HEAD

| Tiêu chí | GET | HEAD |
| --- | --- | --- |
| Mục đích | Lấy nội dung tài nguyên. | Kiểm tra metadata của tài nguyên. |
| Response status | Mã trạng thái theo kết quả xử lý tài nguyên. | Thường tương ứng với GET cho cùng URL và điều kiện request. |
| Response headers | Có. | Có, thường tương ứng với GET. |
| Response body | Có nội dung khi response có body. | Không gửi response body. |
| Tải nội dung tệp về client | Có. | Không. |
| Dùng kiểm tra Content-Type | Được. | Được. |
| Dùng kiểm tra Content-Length | Được. | Được nếu server gửi header này. |
| Dùng đọc HTML/JSON/CSS | Được. | Không; HEAD không trả nội dung để đọc. |
| Method được Simple Web Server hỗ trợ | Có. | Có. |

Theo HTTP semantics, HEAD giống GET ngoại trừ việc server **không được gửi nội dung response**. Server nên gửi các header giống GET, nhưng có thể bỏ header mà giá trị chỉ xác định được trong lúc tạo nội dung. Nếu response HEAD có `Content-Length`, giá trị đó phải bằng số byte mà response GET tương ứng sẽ gửi.

Do đó:

- Không thấy `Content-Length` trong HEAD không tự động có nghĩa request lỗi.
- Nếu có `Content-Length`, hãy hiểu đó là kích thước biểu diễn GET tương ứng, không phải kích thước body HEAD (vì HEAD không có body).
- Không dùng HEAD để xác minh nội dung tệp; dùng GET khi cần đọc hoặc kiểm tra body.

## 6. Đọc các response headers thường gặp

### 6.1. Content-Type

`Content-Type` cho biết kiểu media của biểu diễn được chọn.

Ví dụ:

```http
Content-Type: text/html
```

hoặc:

```http
Content-Type: application/json
```

Simple Web Server dùng bảng MIME tích hợp để suy đoán kiểu nội dung từ phần mở rộng tệp. HEAD có thể giúp kiểm tra kiểu nội dung mà không tải nội dung file.

```sh
curl -I http://127.0.0.1:8080/about.html
curl -I http://127.0.0.1:8080/assets/app.css
curl -I http://127.0.0.1:8080/data/sample.json
```

Kiểu thực tế cần được kiểm tra từ response của JDK đang chạy; đừng chỉ suy đoán từ tên file.

### 6.2. Content-Length

`Content-Length` biểu thị độ dài nội dung response tính theo **byte**, không phải số ký tự.

Ví dụ:

```http
Content-Length: 148
```

Với GET, giá trị này mô tả số byte của response body nếu được gửi theo cách có độ dài xác định. Với HEAD, nếu header được gửi, giá trị phải tương ứng với body mà GET cùng tài nguyên sẽ gửi.

Một ký tự Unicode có thể chiếm nhiều byte trong UTF-8. Vì vậy, không lấy số ký tự nhìn thấy trong HTML rồi so sánh trực tiếp với `Content-Length`.

### 6.3. Last-Modified và các header metadata khác

Một response có thể chứa các header metadata khác, chẳng hạn `Last-Modified`, `Date` hoặc `Location`, tùy loại tài nguyên và xử lý HTTP.

Không phải mọi header đều bắt buộc xuất hiện trong mọi response. Hãy đọc headers thực tế thay vì giả định một danh sách cố định.

### 6.4. Location

`Location` thường xuất hiện trong response redirect.

Ví dụ khi yêu cầu một thư mục thiếu dấu gạch chéo cuối:

```http
HTTP/1.1 301 Moved Permanently
Location: /docs/
```

HEAD tới URL đó cũng có thể nhận status redirect và header `Location`, nhưng không nhận body của response redirect.

Dùng:

```sh
curl -I http://127.0.0.1:8080/docs
curl -I -L http://127.0.0.1:8080/docs
```

Lệnh đầu quan sát redirect ban đầu; lệnh thứ hai yêu cầu curl theo redirect và hiển thị headers của các response trong quá trình đó.

## 7. GET và HEAD với các loại tài nguyên khác nhau

### 7.1. Tệp tồn tại

Với `/about.html`:

```sh
curl -i http://127.0.0.1:8080/about.html
curl -I http://127.0.0.1:8080/about.html
```

Cả hai thường trả `200 OK`. GET trả HTML; HEAD chỉ trả headers.

### 7.2. Thư mục có index file

Giả sử có:

```text
public/
└── docs/
    ├── index.html
    └── guide.html
```

Gửi:

```sh
curl -i http://127.0.0.1:8080/docs/
curl -I http://127.0.0.1:8080/docs/
```

GET trả nội dung index file. HEAD cho biết status và headers của biểu diễn index nhưng không gửi HTML body.

### 7.3. Thư mục không có index file

Nếu thư mục không có index file, GET trả directory listing dạng HTML.

```sh
curl -i http://127.0.0.1:8080/downloads/
curl -I http://127.0.0.1:8080/downloads/
```

HEAD vẫn cho phép kiểm tra status và headers của phản hồi directory listing mà không nhận HTML listing trong body.

Điều này hữu ích khi muốn biết URL thư mục được phục vụ mà không tải danh sách nội dung về client.

### 7.4. Tài nguyên không tồn tại

Gửi:

```sh
curl -i http://127.0.0.1:8080/missing.html
curl -I http://127.0.0.1:8080/missing.html
```

Cả hai thường trả `404 Not Found`. Với GET, response có thể chứa body giải thích lỗi. Với HEAD, status được trả nhưng không có response body.

HEAD hữu ích để kiểm tra trạng thái URL, nhưng không cho bạn nội dung trang lỗi.

### 7.5. Thư mục thiếu dấu gạch chéo cuối

Gửi:

```sh
curl -i http://127.0.0.1:8080/docs
curl -I http://127.0.0.1:8080/docs
```

Nếu `docs` là thư mục, server có thể trả `301 Moved Permanently` với header `Location: /docs/`. Với HEAD, response redirect không có body.

### 7.6. Bảng so sánh theo tài nguyên

| Tài nguyên | GET | HEAD |
| --- | --- | --- |
| Tệp tồn tại | Thường `200` và nội dung tệp. | Thường `200`, headers, không body. |
| Thư mục có index | Nội dung index file. | Headers của biểu diễn index, không body. |
| Thư mục không có index | HTML directory listing. | Headers của phản hồi listing, không body. |
| Tệp không tồn tại | Thường `404`, có thể có body lỗi. | Thường `404`, không body. |
| URL thư mục thiếu dấu `/` | Có thể nhận `301` và body redirect. | Có thể nhận `301` và header Location, không body. |

Status và headers cụ thể phụ thuộc tài nguyên, request và implementation. Hãy kiểm tra response thực tế bằng curl.

## 8. Kiểm tra method bằng log của jwebserver

Mức log mặc định `info` ghi request line và status. Ví dụ log có dạng:

```text
127.0.0.1 - - [27/Nov/2026:05:00:00 +0000] "GET /about.html HTTP/1.1" 200 -
127.0.0.1 - - [27/Nov/2026:05:00:01 +0000] "HEAD /about.html HTTP/1.1" 200 -
```

Khi chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

bạn có thể gửi GET và HEAD từ terminal khác rồi quan sát log. Method trong request line giúp phân biệt hai loại request, còn status cho biết kết quả xử lý.

Nếu cần xem request headers và response headers, chạy với:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o verbose
```

Mức `verbose` bổ sung headers và đường dẫn tuyệt đối tài nguyên được yêu cầu. Hãy rà soát log trước khi chia sẻ vì request headers có thể chứa dữ liệu nhạy cảm.

Mức `none` tắt log từng request; khi dùng mức này, không thể dựa vào console request log để so sánh GET và HEAD.

## 9. Method khác GET/HEAD không được Simple Web Server phục vụ

Simple Web Server là file server tĩnh, không phải API backend. Tài liệu CLI mô tả chỉ phục vụ idempotent GET và HEAD; các method khác nhận `501 Not Implemented` hoặc `405 Method Not Allowed` tùy đường xử lý.

Ví dụ thử POST:

```sh
curl -i -X POST -d "name=demo" http://127.0.0.1:8080/about.html
```

Response thường là một trong các mã không hỗ trợ method, chẳng hạn `405` hoặc `501`. Không dùng POST, PUT hay DELETE để upload, ghi, sửa hoặc xóa tệp qua `jwebserver`.

Java SE 27 API của `SimpleFileServer.createFileHandler` cũng mô tả file handler hỗ trợ HEAD và GET; nếu cần thêm method, lập trình viên phải bổ sung handler riêng hoặc ghép handler bằng API HTTP server.

## 10. Thực hành: đối chiếu GET và HEAD trên cùng tài nguyên

### 10.1. Chuẩn bị document root

Tạo cấu trúc:

```text
demo/
└── public/
    ├── index.html
    ├── about.html
    ├── docs/
    │   └── index.html
    ├── downloads/
    │   ├── sample.txt
    │   └── data.json
    └── assets/
        └── app.css
```

Ví dụ nội dung `public/about.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>GET và HEAD</title>
</head>
<body>
  <h1>Thử nghiệm HTTP method</h1>
  <p>Trang này dùng để so sánh GET và HEAD.</p>
</body>
</html>
```

### 10.2. Khởi động server

Từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

### 10.3. Gửi GET

```sh
curl -i http://127.0.0.1:8080/about.html
```

Ghi lại status, `Content-Type`, `Content-Length` nếu có và nội dung body.

### 10.4. Gửi HEAD

```sh
curl -I http://127.0.0.1:8080/about.html
```

Ghi lại status và headers. Xác nhận terminal không hiển thị HTML body.

### 10.5. So sánh headers của GET và HEAD

Có thể in headers của GET mà không hiển thị body:

```sh
curl -sS -D - -o /dev/null http://127.0.0.1:8080/about.html
```

Sau đó so sánh với:

```sh
curl -sS -I http://127.0.0.1:8080/about.html
```

Kiểm tra các header mô tả cùng biểu diễn. Nếu `Content-Length` xuất hiện ở cả hai response, giá trị của HEAD phải tương ứng với số byte body của GET. Nếu một header được lược bỏ, hãy xem đó có phải header chỉ xác định được trong lúc tạo body hay không.

### 10.6. Kiểm tra các trường hợp khác

```sh
# File tồn tại:
curl -I http://127.0.0.1:8080/assets/app.css

# Thư mục có index:
curl -I http://127.0.0.1:8080/docs/

# Thư mục không có index:
curl -I http://127.0.0.1:8080/downloads/

# Tài nguyên không tồn tại:
curl -I http://127.0.0.1:8080/not-found.txt

# Redirect thư mục:
curl -I http://127.0.0.1:8080/docs
```

Gửi GET tương ứng nếu cần kiểm tra body:

```sh
curl -i http://127.0.0.1:8080/docs/
curl -i http://127.0.0.1:8080/downloads/
curl -i http://127.0.0.1:8080/not-found.txt
```

### 10.7. Bảng ghi kết quả

| URL | GET: status/body | HEAD: status/body | Header cần đối chiếu |
| --- | --- | --- | --- |
| `/about.html` | Ghi status và HTML body. | Ghi status; body rỗng. | `Content-Type`, `Content-Length` nếu có. |
| `/docs/` | Ghi status và index body. | Ghi status; body rỗng. | Metadata của biểu diễn index. |
| `/downloads/` | Ghi status và HTML listing. | Ghi status; body rỗng. | `Content-Type` của listing và headers khác nếu có. |
| `/not-found.txt` | Ghi status lỗi và body nếu có. | Ghi cùng kết quả trạng thái; body rỗng. | Status và headers lỗi nếu có. |
| `/docs` | Ghi status redirect và body nếu có. | Ghi status redirect; body rỗng. | `Location`. |

Sau khi hoàn thành, dừng server bằng **Ctrl+C**.

## 11. Chẩn đoán vấn đề thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `curl -I` chỉ hiển thị headers | Đây là hành vi đúng của HEAD. | Dùng GET nếu cần xem response body. |
| GET trả `200`, HEAD trả status khác | Request không giống nhau, có redirect, điều kiện hoặc khác biệt ở client/proxy. | Gửi cùng URL và điều kiện headers; dùng `curl -v` để xem request thực tế. |
| HEAD không có `Content-Length` | Server có thể lược bỏ header mà giá trị chỉ tính được khi tạo nội dung. | Không kết luận tài nguyên lỗi chỉ từ header này; dùng GET để kiểm tra. |
| `Content-Length` của HEAD khác GET | Request không chọn cùng biểu diễn hoặc có khác biệt response. | So sánh URL, query và request headers; xác minh trên cùng một tài nguyên. |
| HEAD trả `404` | Tài nguyên không tồn tại hoặc không được phục vụ. | Kiểm tra URL path và document root bằng GET/HEAD. |
| Curl báo không kết nối được | Server chưa chạy, sai port hoặc bind address không phù hợp. | Đọc startup banner và dùng đúng URL. |
| POST trả `405` hoặc `501` | Method không được file server hỗ trợ. | Dùng GET/HEAD hoặc xây dựng backend/handler phù hợp. |
| HEAD theo redirect nhưng không thấy body | HEAD không gửi response body kể cả response redirect. | Đọc `Location`; dùng GET nếu cần xem body của response. |
| PowerShell gọi `curl` không có hành vi như ví dụ | `curl` có thể là alias của `Invoke-WebRequest`. | Gọi `curl.exe`. |

## 12. Bài tập tự kiểm tra

1. Gửi GET và HEAD tới cùng một tệp HTML. So sánh status, headers và response body.
2. Dùng `curl -i` và `curl -I`. Giải thích method nào được gửi trong từng lệnh.
3. Dùng `curl -sS -D - -o /dev/null` để in headers của GET nhưng bỏ body ở phía client. Giải thích vì sao thao tác này vẫn là GET.
4. So sánh `Content-Type` của HTML, CSS và JSON qua HEAD.
5. Kiểm tra `Content-Length` của GET và HEAD. Giải thích tại sao giá trị, nếu được gửi trong HEAD, mô tả body GET tương ứng chứ không phải body HEAD.
6. Gửi HEAD tới thư mục có index và thư mục không có index. So sánh status và headers.
7. Gửi HEAD tới tài nguyên không tồn tại. Giải thích vì sao response không có body nhưng vẫn thể hiện lỗi bằng status.
8. Gửi HEAD tới URL thư mục thiếu dấu `/`. Đọc header `Location`.
9. Gửi POST tới một tệp tĩnh và giải thích vì sao `jwebserver` không phải API upload.
10. Chạy server với mức log `info` và quan sát method trong request log.

**Tiêu chí hoàn thành:** bạn phân biệt chính xác GET và HEAD, dùng curl gửi đúng method, đọc status và response headers, hiểu quy tắc body rỗng của HEAD, diễn giải Content-Type/Content-Length/Location và nhận biết giới hạn method của Simple Web Server.

## 13. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): xác nhận Simple Web Server chỉ phục vụ HEAD và GET; method khác nhận 501 hoặc 405.
- [Oracle Java SE 27 — SimpleFileServer API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): mô tả file handler hỗ trợ HEAD và GET; có thể bổ sung handler khác khi cần method bổ sung.
- [RFC 9110 — HTTP Semantics, Section 9.3.2 HEAD](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.2): định nghĩa HEAD giống GET nhưng không được gửi response content; giải thích các header trong response HEAD.
- [curl — Command line options](https://curl.se/docs/manpage.html): mô tả tùy chọn `-I`/`--head`, `-i`/`--include`, `-D`/`--dump-header` và `-o`/`--output`.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục đích và phạm vi của Simple Web Server được giới thiệu trong Java 18.
