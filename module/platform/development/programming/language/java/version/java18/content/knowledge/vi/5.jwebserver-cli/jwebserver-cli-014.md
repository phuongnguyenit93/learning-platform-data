# Phương thức HTTP không hỗ trợ: kiểm chứng 405 hoặc 501 theo lớp xử lý của máy chủ

## 1. Giới hạn method của Simple Web Server

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tệp tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ vẫn có trong các JDK hiện đại, bao gồm JDK 27.

Simple Web Server chỉ phục vụ hai HTTP method:

- **GET:** lấy nội dung tài nguyên tĩnh.
- **HEAD:** lấy status và response headers tương ứng, không nhận response body.

Các method khác như POST, PUT, DELETE, OPTIONS hoặc một method mở rộng không được dùng để ghi, sửa, xóa hay xử lý nghiệp vụ trên tài nguyên. Khi nhận method ngoài phạm vi hỗ trợ, server có thể trả **405 Method Not Allowed** hoặc **501 Not Implemented**, tùy lớp xử lý nhận request.

Điểm cần nhớ là hai status này không đồng nghĩa:

- `405` nói rằng method được máy chủ nhận biết nhưng không được phép trên tài nguyên đang yêu cầu.
- `501` nói rằng máy chủ không nhận biết hoặc không triển khai chức năng cần thiết cho method đó.

Tài liệu lệnh `jwebserver` nêu rõ các request ngoài GET/HEAD nhận 501 hoặc 405. Trong khi đó, hợp đồng API của `SimpleFileServer.createFileHandler` quy định file handler trả 405 cho mọi method ngoài GET/HEAD. Phần sau sẽ tách hai lớp này và chỉ cách kiểm tra trên JDK đang chạy.

> **Phạm vi:** Simple Web Server chỉ phục vụ tệp tĩnh qua HTTP/1.1. Công cụ không cung cấp HTTPS, HTTP/2, xác thực người dùng hay xử lý nghiệp vụ web động; phù hợp cho phát triển, thử nghiệm và gỡ lỗi, không dùng làm máy chủ production.

## 2. Phân biệt 405 và 501 theo HTTP

### 2.1. 405 Method Not Allowed

HTTP status `405 Method Not Allowed` cho biết method xuất hiện trong request line được origin server nhận biết, nhưng target resource không hỗ trợ method đó.

Ví dụ:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
Content-Length: 0
```

Header quan trọng là `Allow`. Theo RFC 9110, server **MUST** gửi `Allow` trong response 405 để liệt kê những method hiện được tài nguyên cho phép.

Với file handler mặc định của Simple Web Server, danh sách được hỗ trợ là GET và HEAD. Vì vậy, nếu nhận 405, hãy kiểm tra header `Allow` để xác nhận những method mà handler quảng bá.

### 2.2. 501 Not Implemented

HTTP status `501 Not Implemented` cho biết server không hỗ trợ chức năng cần thiết để hoàn thành request. Đây là phản hồi phù hợp khi server không nhận biết method hoặc không có khả năng hỗ trợ method đó trên bất kỳ tài nguyên nào.

Ví dụ:

```http
HTTP/1.1 501 Not Implemented
Content-Length: 0
```

Khác với 405, RFC 9110 không yêu cầu 501 phải có header `Allow`. Server có thể gửi body giải thích, nhưng client không nên dựa vào nội dung body để phân loại status.

### 2.3. Bảng so sánh

| Tiêu chí | 405 Method Not Allowed | 501 Not Implemented |
| --- | --- | --- |
| Ý nghĩa | Method được nhận biết nhưng không được target resource cho phép. | Server không nhận biết hoặc không triển khai chức năng của method. |
| Lớp xử lý thường liên quan | Handler đã nhận request và từ chối method cho tài nguyên. | Server hoặc lớp xử lý không có implementation cho method. |
| Header Allow | Bắt buộc theo RFC 9110. | Không bắt buộc. |
| Với SimpleFileServer API | File handler trả 405 cho method ngoài GET/HEAD. | Không phải status được hợp đồng createFileHandler mô tả cho trường hợp này. |
| Với lệnh jwebserver | Có thể xuất hiện. | Có thể xuất hiện. |

Đừng suy luận rằng 405 luôn có nghĩa tệp không tồn tại hoặc 501 luôn có nghĩa URL sai. Hai status này mô tả khả năng xử lý method; chúng không thay thế status 404 của tài nguyên không tìm thấy.

## 3. Vì sao tài liệu CLI ghi cả 405 và 501?

Cần phân biệt **lệnh CLI** và **API file handler**:

1. Lệnh `jwebserver` khởi động một máy chủ mặc định, dùng để phục vụ cây tệp tĩnh. Tài liệu CLI chỉ rõ GET và HEAD được phục vụ; các method khác có thể nhận 501 hoặc 405.
2. API `SimpleFileServer.createFileHandler(rootDirectory)` tạo một `HttpHandler` phục vụ tệp và directory listing. Hợp đồng API ghi rõ handler chỉ hỗ trợ HEAD/GET và trả 405 cho method khác.
3. Khi lập trình với `HttpServer`, bạn có thể thêm handler riêng cho method khác rồi chuyển các request còn lại tới file handler. Khi đó ứng dụng của bạn đã mở rộng cách xử lý so với lệnh CLI mặc định.

Theo HTTP semantics, server nên trả 501 nếu method không được nhận biết hoặc không được triển khai; trả 405 nếu method được nhận biết và triển khai ở máy chủ nhưng không được target resource cho phép. Vì vậy, đừng mặc định mọi method ngoài GET/HEAD trên mọi phiên bản JDK đều phải cho cùng một status. Hãy đối chiếu tài liệu của lớp đang dùng và kiểm tra response thực tế.

### 3.1. Hợp đồng của createFileHandler

Tài liệu Java SE 27 mô tả:

- Handler phục vụ tệp và directory listing.
- Handler chỉ hỗ trợ method HEAD và GET.
- Với mọi method khác, handler trả status 405.

Điều này rất rõ khi bạn tự tạo file handler trong Java. Nếu gọi trực tiếp handler mặc định, kỳ vọng theo hợp đồng API là 405.

### 3.2. Hợp đồng của jwebserver CLI

Tài liệu lệnh mô tả ở mức công cụ:

- Chỉ các request idempotent HEAD và GET được phục vụ.
- Request khác nhận 501 hoặc 405.

Đây là mô tả có chủ ý bao quát kết quả từ lớp xử lý mặc định. Khi quan sát một status cụ thể, hãy ghi lại JDK version, method, response headers và status; không biến một lần thử nghiệm trên một máy thành quy tắc tuyệt đối cho mọi bản JDK.

## 4. Các method thường dùng nhưng jwebserver không xử lý

| Method | Ý nghĩa HTTP tổng quát | Vì sao không phù hợp với file server mặc định |
| --- | --- | --- |
| GET | Lấy biểu diễn của tài nguyên. | Được hỗ trợ. |
| HEAD | Như GET nhưng không truyền response body. | Được hỗ trợ. |
| POST | Gửi nội dung để server xử lý theo tài nguyên. | Không có logic xử lý nghiệp vụ hoặc tạo tài nguyên. |
| PUT | Tạo hoặc thay thế biểu diễn tại URI đích. | Không có chức năng ghi tệp từ request body. |
| DELETE | Xóa biểu diễn của tài nguyên. | Không có chức năng xóa tệp. |
| OPTIONS | Hỏi các tùy chọn giao tiếp của tài nguyên. | CLI mặc định không triển khai OPTIONS/CORS preflight. |
| TRACE | Kiểm tra vòng lặp thông điệp qua đường đi tới server. | Không nằm trong hai method được file server phục vụ. |
| CONNECT | Thiết lập tunnel tới server đích. | Không phải chức năng của HTTP static file server. |
| PATCH | Áp dụng thay đổi một phần lên biểu diễn. | Không có logic cập nhật nội dung tệp. |

HTTP có nhiều method ngoài GET/HEAD. Việc một method được chuẩn hóa hoặc được dùng phổ biến không có nghĩa Simple Web Server phải triển khai method đó. Theo thiết kế, công cụ này tập trung vào việc đọc tài nguyên tĩnh.

## 5. Chuẩn bị môi trường kiểm thử

Tạo document root đơn giản:

```text
demo/
└── public/
    ├── index.html
    └── sample.txt
```

Nội dung `public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>HTTP method test</title>
</head>
<body>
  <h1>Simple Web Server</h1>
  <p>Kiểm tra method GET, HEAD và method không hỗ trợ.</p>
</body>
</html>
```

Nội dung `public/sample.txt`:

```text
Static file for HTTP method tests.
```

Từ thư mục `demo`, khởi động server:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Đọc startup banner để xác nhận server dùng cổng `8080` và document root đúng thư mục `public`. Giữ terminal này mở để quan sát request log.

Dùng địa chỉ loopback để các phép thử chỉ kết nối tới máy đang chạy server. Không cần bind wildcard hoặc mở cổng ra mạng LAN cho bài thực hành này.

## 6. Xác nhận hai method được hỗ trợ

Trước khi thử method không hỗ trợ, hãy tạo mốc so sánh bằng GET và HEAD.

### 6.1. GET trả nội dung tệp

```sh
curl --http1.1 -i http://127.0.0.1:8080/sample.txt
```

Kết quả thành công thường có status `200 OK`, các response headers như `Content-Type`, `Content-Length` và response body chứa nội dung tệp.

### 6.2. HEAD chỉ trả headers

```sh
curl --http1.1 -I http://127.0.0.1:8080/sample.txt
```

Kết quả thường có status `200 OK` và headers tương ứng, nhưng không có response body.

Hai request này xác nhận server đang chạy và tài nguyên thử nghiệm có thể truy cập qua method được hỗ trợ.

## 7. Kiểm tra 405 bằng method đã được nhận biết

Dùng POST, PUT hoặc DELETE để gửi request tới cùng tài nguyên:

```sh
curl --http1.1 -i -X POST --data-binary "name=demo" http://127.0.0.1:8080/sample.txt
```

```sh
curl --http1.1 -i -X PUT --data-binary "replacement content" http://127.0.0.1:8080/sample.txt
```

```sh
curl --http1.1 -i -X DELETE http://127.0.0.1:8080/sample.txt
```

Trong các ví dụ này:

- `-X` hoặc `--request` đặt method được gửi.
- `--data-binary` gửi request body cho POST/PUT.
- `-i` hiển thị response headers cùng body nếu có.
- `--http1.1` cố định phiên bản giao thức để phép thử phù hợp với phạm vi hỗ trợ của `jwebserver`.

Nếu lớp xử lý trả 405, response có dạng:

```http
HTTP/1.1 405 Method Not Allowed
Allow: HEAD, GET
```

Thứ tự các method trong header có thể khác. Điều cần xác minh là header `Allow` có liệt kê những method được phép, thông thường là GET và HEAD.

### 7.1. Đừng nhầm request body với thao tác ghi tệp

Việc gửi `--data-binary` không làm `jwebserver` tự động lưu nội dung vào tệp. Server chỉ nhận request; file handler mặc định không có chức năng upload hoặc thay thế tệp.

Sau khi thử PUT hoặc DELETE, kiểm tra lại bằng GET nếu muốn xác nhận tệp gốc vẫn được phục vụ như trước. Không sử dụng một file server tĩnh như endpoint upload.

### 7.2. Kiểm tra OPTIONS

```sh
curl --http1.1 -i -X OPTIONS http://127.0.0.1:8080/sample.txt
```

OPTIONS là method hợp lệ trong HTTP và được định nghĩa là method safe, nhưng vẫn nằm ngoài phạm vi GET/HEAD của Simple Web Server. Vì vậy, nó có thể bị từ chối bằng 405 hoặc 501 theo lớp xử lý.

Điều này cũng quan trọng với CORS: trình duyệt có thể gửi request OPTIONS preflight trước một cross-origin request. `jwebserver` mặc định không cung cấp handler CORS hoặc phản hồi preflight cần thiết, nên không thể xem nó như backend CORS hoàn chỉnh.

## 8. Kiểm tra 501 bằng method không được nhận biết

HTTP cho phép mở rộng method bằng token mới. Để quan sát cách server xử lý một method không quen thuộc, thử một token giả định như `FROB`:

```sh
curl --http1.1 -i -X FROB http://127.0.0.1:8080/sample.txt
```

Theo HTTP semantics, nếu server không nhận biết hoặc không triển khai method đó, phản hồi phù hợp là:

```http
HTTP/1.1 501 Not Implemented
```

Tài liệu CLI của `jwebserver` cho biết method ngoài GET/HEAD có thể nhận 501 hoặc 405. Vì vậy, hãy ghi nhận status thực tế từ JDK đang dùng. Nếu method lạ được một lớp xử lý hoặc proxy trung gian chặn trước, status bạn quan sát được có thể đến từ lớp đó thay vì file handler.

### 8.1. Xác nhận request đã gửi đúng method

Dùng verbose của curl:

```sh
curl --http1.1 -v -X FROB http://127.0.0.1:8080/sample.txt
```

Trong output, tìm request line:

```http
> FROB /sample.txt HTTP/1.1
```

Điều này xác nhận curl đã gửi method mong muốn. Dòng response bắt đầu bằng `<` cho biết status server trả về.

Nếu cần kiểm tra kết nối trực tiếp tới loopback, có thể thêm `--noproxy "*"` để tránh cấu hình proxy của máy tác động tới request:

```sh
curl --noproxy "*" --http1.1 -i -X FROB http://127.0.0.1:8080/sample.txt
```

## 9. Đọc header Allow và diễn giải response

### 9.1. Allow trong response 405

Theo RFC 9110, response 405 bắt buộc có header `Allow`. Ví dụ:

```http
HTTP/1.1 405 Method Not Allowed
Allow: HEAD, GET
```

Đọc header này để biết các method được phép tại tài nguyên. Với file handler mặc định, bạn thường thấy GET và HEAD.

Không nên chỉ nhìn status line rồi bỏ qua headers. `Allow` cung cấp thông tin máy khách có thể dùng để chọn method khác.

### 9.2. 501 không yêu cầu Allow

Response 501 nói rằng server không hỗ trợ chức năng cần thiết cho method. RFC không yêu cầu 501 phải có `Allow`. Vì vậy, nếu response 501 không có header này, đó không tự động là lỗi định dạng.

### 9.3. Bảng diễn giải

| Quan sát | Diễn giải |
| --- | --- |
| `405` và `Allow: GET, HEAD` | Method bị từ chối tại tài nguyên; header công bố các method được phép. |
| `405` không có `Allow` | Kiểm tra lại response có đến từ server/handler khác hoặc qua proxy không; RFC yêu cầu Allow trong 405. |
| `501` | Server hoặc lớp xử lý không nhận biết/triển khai method. |
| `404` | Tài nguyên không tìm thấy hoặc server không muốn tiết lộ sự tồn tại; đây không phải kết quả kiểm tra method thuần túy. |
| `403` | Request bị từ chối vì chính sách truy cập; không đồng nghĩa method không được hỗ trợ. |
| Không nhận được HTTP status | Có thể kết nối, cú pháp request hoặc giao thức gặp lỗi trước khi handler trả response. |

## 10. Quan sát request log của jwebserver

Mức log mặc định `info` ghi request line và status. Sau khi gửi GET, HEAD, POST và method lạ, terminal server có thể hiển thị các dòng tương tự:

```text
127.0.0.1 - - [27/Nov/2026:05:00:00 +0000] "GET /sample.txt HTTP/1.1" 200 -
127.0.0.1 - - [27/Nov/2026:05:00:01 +0000] "HEAD /sample.txt HTTP/1.1" 200 -
127.0.0.1 - - [27/Nov/2026:05:00:02 +0000] "POST /sample.txt HTTP/1.1" 405 -
127.0.0.1 - - [27/Nov/2026:05:00:03 +0000] "FROB /sample.txt HTTP/1.1" 501 -
```

Đây là dữ liệu minh họa; status thật phụ thuộc method và lớp xử lý của JDK.

Nếu cần thêm thông tin header, khởi động lại server với:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o verbose
```

Mức `verbose` bổ sung request headers, response headers và đường dẫn tuyệt đối của tài nguyên được yêu cầu. Rà soát log trước khi chia sẻ vì request headers có thể chứa dữ liệu nhạy cảm.

Mức `none` tắt log từng request. Nếu chọn mức này, hãy dùng output của curl để kiểm tra method và status.

## 11. Phân biệt lỗi method với lỗi tài nguyên

Một số lỗi HTTP có thể xuất hiện trong cùng quá trình thử nghiệm nhưng mang ý nghĩa khác nhau:

| Status | Ý nghĩa | Ví dụ trong bài |
| --- | --- | --- |
| `200 OK` | Request được xử lý thành công. | GET tệp tồn tại. |
| `301 Moved Permanently` | URL được chuyển hướng. | Yêu cầu directory thiếu dấu `/` cuối. |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc không tiết lộ rằng tài nguyên tồn tại. | GET đường dẫn không có tệp. |
| `405 Method Not Allowed` | Method được nhận biết nhưng không được tài nguyên cho phép. | POST/PUT tới file handler mặc định. |
| `501 Not Implemented` | Server không nhận biết hoặc không triển khai method. | Method mở rộng không được hỗ trợ. |
| `400 Bad Request` | Request không hợp lệ ở cấp giao thức/cú pháp. | Request line hoặc header sai định dạng. |

Khi status là 405 hoặc 501, không nên đổi tên tệp hoặc thay document root để “sửa lỗi”. Trước tiên hãy xác định method đã gửi và lớp xử lý đã tạo response.

## 12. Khi nào cần mở rộng bằng API thay vì dùng CLI?

Nếu ứng dụng cần POST, PUT hoặc DELETE, lệnh CLI `jwebserver` không có tùy chọn bật các method này. Bạn cần xây dựng server bằng API `com.sun.net.httpserver` và tự đăng ký handler phù hợp.

Java SE 27 cung cấp `HttpHandlers.handleOrElse` để chọn handler theo điều kiện. Có thể kết hợp một handler riêng với file handler:

```java
var fileHandler =
    SimpleFileServer.createFileHandler(Path.of("public").toAbsolutePath());

var handler = HttpHandlers.handleOrElse(
    request -> request.getRequestMethod().equals("PUT"),
    exchange -> {
        // Validate the request, authorize the caller,
        // process the body, persist the resource, and send a response.
    },
    fileHandler
);
```

Đoạn mã minh họa cách định tuyến PUT tới handler riêng; phần xử lý bên trong phải được triển khai đầy đủ. Handler tùy chỉnh cần kiểm tra danh tính, quyền, đường dẫn, kích thước và nội dung request trước khi ghi dữ liệu.

Các request không khớp điều kiện PUT được chuyển tới file handler. Nếu method vẫn ngoài GET/HEAD, file handler mặc định sẽ từ chối theo hợp đồng API.

Đây là cách mở rộng ở cấp Java API, không phải một tùy chọn cấu hình có sẵn của CLI.

## 13. Thực hành tổng hợp

### 13.1. Khởi động

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

### 13.2. Gửi các method

```sh
# Method được hỗ trợ:
curl --http1.1 -i http://127.0.0.1:8080/sample.txt
curl --http1.1 -I http://127.0.0.1:8080/sample.txt

# Method đã biết nhưng không được file server phục vụ:
curl --http1.1 -i -X POST --data-binary "demo" http://127.0.0.1:8080/sample.txt
curl --http1.1 -i -X PUT --data-binary "demo" http://127.0.0.1:8080/sample.txt
curl --http1.1 -i -X DELETE http://127.0.0.1:8080/sample.txt
curl --http1.1 -i -X OPTIONS http://127.0.0.1:8080/sample.txt

# Method mở rộng không quen thuộc:
curl --http1.1 -i -X FROB http://127.0.0.1:8080/sample.txt
```

### 13.3. Ghi kết quả

| Method | Status nhận được | Allow header | Kết luận |
| --- | --- | --- | --- |
| GET | Ghi kết quả | Ghi nếu có | Method được hỗ trợ. |
| HEAD | Ghi kết quả | Ghi nếu có | Method được hỗ trợ. |
| POST | Ghi kết quả | Ghi nếu có | Kiểm tra 405/501. |
| PUT | Ghi kết quả | Ghi nếu có | Kiểm tra 405/501. |
| DELETE | Ghi kết quả | Ghi nếu có | Kiểm tra 405/501. |
| OPTIONS | Ghi kết quả | Ghi nếu có | Kiểm tra 405/501. |
| FROB | Ghi kết quả | Ghi nếu có | Kiểm tra cách server xử lý method không nhận biết. |

Khi kết thúc, dừng server bằng **Ctrl+C**.

## 14. Chẩn đoán vấn đề thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| POST trả 405 | File handler nhận biết request nhưng không cho phép method trên tài nguyên. | Đọc header `Allow`; dùng GET/HEAD hoặc viết handler riêng. |
| POST trả 501 | Lớp xử lý của CLI không triển khai method theo cách phân loại của nó. | Đối chiếu tài liệu CLI của JDK và ghi lại status thực tế. |
| Method lạ trả 501 | Server không nhận biết method hoặc không triển khai chức năng đó. | Đây là phản hồi phù hợp theo RFC 9110. |
| Method lạ trả 405 | Lớp xử lý đã chuyển request tới handler từ chối method. | Đọc `Allow` và xác định handler đang xử lý. |
| Response 405 không có Allow | Có thể response đến từ proxy/handler khác hoặc implementation không đáp ứng yêu cầu RFC. | Dùng curl trực tiếp tới loopback và kiểm tra response headers. |
| OPTIONS bị từ chối | CLI mặc định không có OPTIONS handler. | Nếu cần CORS/preflight, xây dựng handler hoặc dùng server có hỗ trợ CORS. |
| PUT không tạo hoặc thay nội dung file | Simple Web Server không phải file upload server. | Dùng backend/API có kiểm tra quyền và xử lý ghi rõ ràng. |
| Curl không gửi đúng method như mong muốn | Cú pháp lệnh hoặc alias shell làm thay đổi cách gọi. | Dùng `curl.exe` trên PowerShell và `-v` để xem request line. |
| Browser cho kết quả khác curl | Browser có thể gửi OPTIONS preflight hoặc request qua proxy/cache. | Kiểm tra Network panel và thử trực tiếp bằng curl tới loopback. |
| Không thấy request trong terminal | Server chạy `-o none` hoặc request không tới đúng tiến trình. | Dùng `-o info`, xác nhận port và URL. |

## 15. Bài tập tự kiểm tra

1. Gửi GET và HEAD tới cùng một tệp. Ghi status và giải thích vì sao hai method được phục vụ.
2. Gửi POST với request body. Xác nhận body không được lưu vào tệp bởi CLI mặc định.
3. Gửi PUT và DELETE tới một tệp. Phân biệt status method với trạng thái tồn tại của tệp.
4. Gửi OPTIONS và giải thích vì sao một method safe vẫn có thể không được Simple Web Server hỗ trợ.
5. Gửi method giả định `FROB`. Quan sát server trả 405 hay 501 và giải thích kết quả theo RFC 9110.
6. Khi nhận 405, tìm header `Allow` và giải thích vai trò của header này.
7. Khi nhận 501, giải thích vì sao header `Allow` không bắt buộc.
8. So sánh hợp đồng của `SimpleFileServer.createFileHandler` với mô tả tổng quát của lệnh `jwebserver`.
9. Dùng log `info` để đối chiếu request line và status với output của curl.
10. Giải thích cách mở rộng bằng `HttpHandlers.handleOrElse` khi ứng dụng cần một handler PUT riêng.

**Tiêu chí hoàn thành:** bạn phân biệt được 405 và 501 theo HTTP semantics, hiểu vì sao tài liệu CLI cho phép cả hai, biết hợp đồng 405 của file handler API, kiểm tra được method và header Allow bằng curl, đồng thời nhận ra giới hạn của Simple Web Server khi cần xử lý ghi dữ liệu hoặc CORS.

## 16. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): xác nhận CLI chỉ phục vụ HEAD/GET và các method khác có thể nhận 501 hoặc 405.
- [Oracle Java SE 27 — SimpleFileServer API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): hợp đồng của `createFileHandler`, chỉ hỗ trợ HEAD/GET và trả 405 cho method khác; hướng mở rộng bằng handler bổ sung.
- [Oracle Java SE 27 — HttpHandlers API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): API ghép handler theo điều kiện.
- [RFC 9110 — HTTP Semantics, Section 9.1 and 9.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.1): quy tắc method, method extensibility và các method chuẩn.
- [RFC 9110 — Section 10.2.1 Allow](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.1): ý nghĩa và yêu cầu của header `Allow`.
- [RFC 9110 — Section 15.5.6 405 Method Not Allowed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.6): định nghĩa status 405 và yêu cầu gửi Allow.
- [RFC 9110 — Section 15.6.2 501 Not Implemented](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.6.2): định nghĩa status 501.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục đích và phạm vi thiết kế của Simple Web Server được giới thiệu trong Java 18.
