# MIME type tự nhận diện, kiểu mặc định và giới hạn khi không có khai báo charset phù hợp

## 1. MIME type và charset giải quyết hai câu hỏi khác nhau

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tệp tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ này vẫn được hỗ trợ trên các JDK hiện đại, bao gồm JDK 27.

Khi server trả một tệp, header `Content-Type` cho client biết **dữ liệu thuộc định dạng nào**. Ví dụ:

```http
Content-Type: text/html
```

Header này cho biết nội dung là HTML. Tuy nhiên, nó chưa nhất thiết cho biết các byte bên trong văn bản được mã hóa bằng UTF-8, US-ASCII hay một charset khác.

Hai khái niệm cần phân biệt:

- **MIME type (media type):** mô tả định dạng biểu diễn, ví dụ `text/html`, `text/plain`, `image/png`.
- **Charset:** mô tả cách giải mã byte thành ký tự, ví dụ `UTF-8` hoặc `US-ASCII`.

Khi cần khai báo cả hai, HTTP dùng tham số `charset` trong `Content-Type`:

```http
Content-Type: text/html; charset=UTF-8
```

Simple Web Server tự nhận diện MIME type bằng bảng tích hợp. Việc nhận diện này không đồng nghĩa server luôn bổ sung charset phù hợp cho mọi tệp văn bản.

> **Phạm vi:** Simple Web Server chỉ phục vụ tài nguyên tĩnh qua HTTP/1.1, phù hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hoặc xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. jwebserver nhận diện MIME type bằng cách nào?

Tài liệu Oracle mô tả MIME type được cấu hình tự động bằng **bảng MIME tích hợp**. Hai ví dụ được nêu rõ:

| Phần mở rộng | MIME type |
| --- | --- |
| `.html` | `text/html` |
| `.java` | `text/plain` |

Điều này cho thấy server dùng thông tin tên tệp/phần mở rộng để chọn một MIME type phù hợp. Với file handler của `SimpleFileServer`, API mô tả kiểu nội dung là kết quả phỏng đoán tốt nhất từ `mimeTable` dùng chung của hệ thống.

Quy trình có thể hình dung:

```text
HTTP GET /index.html
        |
        v
Ánh xạ URI vào tệp trong document root
        |
        v
Lấy tên tệp / phần mở rộng
        |
        v
Tra bảng MIME tích hợp
        |
        +------------------------+
        |                        |
   Có mapping              Không có mapping
        |                        |
        v                        v
   text/html           application/octet-stream
        |                        |
        +------------+-----------+
                     |
                     v
        Đặt Content-Type trong response
                     |
                     v
             Gửi byte của tệp
```

Điểm quan trọng: server **không cần đọc và phân tích nội dung HTML, Java hoặc ảnh để đoán định dạng**. Nếu tệp được đặt tên sai phần mở rộng, MIME type có thể không phù hợp với dữ liệu thực tế.

Ví dụ, nếu một tệp JSON được đặt tên `payload.bin`, server có thể chọn MIME type theo phần mở rộng `.bin`, không tự kiểm tra nội dung để kết luận đó là JSON.

## 3. Các ví dụ MIME type và ý nghĩa khi trình duyệt nhận tệp

Một số media type thường gặp:

| MIME type | Dữ liệu được mô tả | Cách dùng thường gặp |
| --- | --- | --- |
| `text/html` | Tài liệu HTML | Trình duyệt phân tích và hiển thị trang. |
| `text/plain` | Văn bản thuần | Hiển thị nội dung văn bản, không phân tích như HTML. |
| `text/css` | Stylesheet CSS | Dùng trong phần tử `link` để tạo kiểu trang. |
| `text/javascript` | JavaScript | Dùng cho script theo ngữ cảnh hỗ trợ. |
| `application/json` | Dữ liệu JSON | Được client phân tích như dữ liệu JSON. |
| `image/png` | Ảnh PNG | Hiển thị ảnh. |
| `image/jpeg` | Ảnh JPEG | Hiển thị ảnh. |
| `application/pdf` | Tài liệu PDF | Trình duyệt có thể mở bằng trình xem PDF hoặc tải xuống. |
| `application/octet-stream` | Dữ liệu nhị phân tổng quát | Client thường coi là dữ liệu tải xuống, không phải một định dạng hiển thị cụ thể. |

Bảng trên giải thích ý nghĩa media type, không phải cam kết rằng mọi phần mở rộng tương ứng đều có mặt trong bảng MIME của mọi bản JDK hoặc mọi hệ thống. Hãy kiểm tra `Content-Type` thực tế bằng HTTP response khi cần xác nhận mapping.

Đặc biệt, `.java` được tài liệu Oracle nêu là `text/plain`. Điều đó có nghĩa server gửi nội dung source file như văn bản tĩnh; nó **không biên dịch, không chạy mã Java và không biến tệp thành ứng dụng Java**.

## 4. Kiểu mặc định khi không tìm được MIME type

Nếu bảng MIME không có mapping cho tên tệp, implementation của Simple Web Server dùng kiểu mặc định:

```http
Content-Type: application/octet-stream
```

`application/octet-stream` biểu thị một luồng byte tổng quát, không khẳng định nội dung là HTML, ảnh, PDF hay một định dạng văn bản cụ thể.

Ví dụ, tạo tệp:

```text
public/
└── mystery.customdata
```

Nếu phần mở rộng không có trong bảng MIME, response có dạng:

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
```

Client vẫn có thể tải byte của tệp. Trình duyệt thường tải loại nội dung này xuống thay vì hiển thị nó như một trang HTML.

### 4.1. Kiểu mặc định không phải text/plain

Không nên giả định tệp không rõ phần mở rộng sẽ tự động được coi là văn bản. Với Simple Web Server, fallback được implementation sử dụng là `application/octet-stream`.

Ví dụ:

| Tên tệp | Mapping có thể quan sát |
| --- | --- |
| `page.html` | `text/html` theo ví dụ Oracle. |
| `Source.java` | `text/plain` theo ví dụ Oracle. |
| `unknown.customdata` | `application/octet-stream` nếu không có mapping. |

Nếu muốn một tệp không có phần mở rộng được hiển thị như văn bản, cần một cấu hình hoặc handler có khả năng đặt đúng `Content-Type`. Không đổi phần mở rộng một cách tùy tiện nếu định dạng nội dung không khớp.

### 4.2. Fallback không phân tích nội dung

Giả sử `image-data.unknown` thực chất chứa byte PNG. Nếu không có mapping cho phần mở rộng, server vẫn có thể gửi `application/octet-stream`. Nó không tự kiểm tra chữ ký byte PNG để thay header thành `image/png`.

Ngược lại, đặt tên một tệp văn bản thành `report.html` có thể khiến server gửi `text/html`, dù nội dung không phải HTML hợp lệ.

Vì vậy, tên tệp, định dạng nội dung và MIME type cần nhất quán.

## 5. Kiểm tra MIME type bằng curl

Dùng `curl -I` để gửi HEAD và xem response headers mà không tải body về terminal.

Khởi động server:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Kiểm tra các tệp:

```sh
curl -I http://127.0.0.1:8080/index.html
curl -I http://127.0.0.1:8080/Example.java
curl -I http://127.0.0.1:8080/mystery.customdata
```

Tập trung vào header:

```http
Content-Type: text/html
```

hoặc:

```http
Content-Type: text/plain
```

hoặc:

```http
Content-Type: application/octet-stream
```

Nếu cần xác nhận cả nội dung, dùng GET:

```sh
curl -i http://127.0.0.1:8080/index.html
```

`-i` hiển thị response headers và response body. Khi kiểm tra mapping, không chỉ nhìn cách trình duyệt hiển thị tệp: hãy đọc header `Content-Type` để biết server đã khai báo loại dữ liệu nào.

### 5.1. Đừng nhầm Content-Type với Content-Encoding

Hai header có mục đích khác nhau:

| Header | Ý nghĩa |
| --- | --- |
| `Content-Type` | Định dạng dữ liệu, có thể kèm tham số charset. |
| `Content-Encoding` | Cách biểu diễn đã được mã hóa/nén ở tầng HTTP, ví dụ gzip. |

Ví dụ:

```http
Content-Type: text/html; charset=UTF-8
Content-Encoding: gzip
```

Trong ví dụ này, dữ liệu là HTML được nén gzip; sau khi giải nén, byte HTML được giải mã theo UTF-8. Charset không phải thuật toán nén.

## 6. Vì sao MIME type không tự giải quyết charset?

Một MIME type như `text/html` cho biết định dạng là HTML. Nó không nhất thiết cho biết byte của tệp được mã hóa bằng charset nào.

Ví dụ cùng một câu tiếng Việt:

```text
Xin chào, Java 18!
```

có thể được lưu bằng UTF-8 hoặc một charset khác. Byte của hai cách mã hóa khác nhau. Nếu client giải mã bằng charset không trùng với cách tệp được lưu, nội dung có thể thành ký tự lỗi hoặc dấu tiếng Việt bị sai.

Để khai báo charset trong HTTP, server có thể gửi:

```http
Content-Type: text/plain; charset=UTF-8
```

Tuy nhiên, MIME mapping cơ bản của `jwebserver` thường chọn media type theo bảng tích hợp. Đừng suy ra rằng vì server chạy trên JDK 18+ thì mọi response `text/*` sẽ tự động có `charset=UTF-8`.

## 7. JEP 400: UTF-8 mặc định của Java không phải charset HTTP

Từ **JDK 18**, UTF-8 là charset mặc định cho các Java SE API phụ thuộc default charset. Ví dụ:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
```

Trên JDK hiện đại, kết quả mặc định là:

```text
UTF-8
```

Điều này có ích khi chương trình Java đọc/ghi văn bản qua những API dùng default charset, chẳng hạn một số constructor của `FileReader`, `FileWriter`, `InputStreamReader` hoặc `OutputStreamWriter`.

Nhưng cần phân biệt hai việc:

- **Default charset của Java:** quy định cách các API Java liên quan giải mã hoặc mã hóa văn bản khi không truyền charset tường minh.
- **Charset trong HTTP Content-Type:** metadata được server gửi cho client để client biết cách giải mã phần văn bản trong response.

Simple Web Server phục vụ tệp tĩnh bằng cách gửi byte của tệp. Nó không đọc toàn bộ tệp văn bản thành String rồi mã hóa lại bằng `Charset.defaultCharset()`. Vì thế JEP 400 không tự thêm `; charset=UTF-8` vào header của tệp tĩnh.

Đây là ranh giới quan trọng khi học Java 18: UTF-8 mặc định giúp hành vi I/O Java nhất quán, nhưng không thay thế hợp đồng MIME/HTTP và không sửa encoding của tệp đã lưu sai.

## 8. Charset của HTML: dùng khai báo trong tài liệu

HTML có thể khai báo encoding ngay trong nội dung bằng phần tử `meta`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiểm tra UTF-8</title>
</head>
<body>
  <h1>Xin chào!</h1>
  <p>Tiếng Việt: ă â ê ô ơ ư đ.</p>
</body>
</html>
```

Khi server trả:

```http
Content-Type: text/html
```

trình duyệt có thể đọc khai báo `meta charset` trong tài liệu để xác định UTF-8. Theo HTML Standard, khai báo charset bằng `meta` phải xuất hiện trong **1.024 byte đầu tiên** của tài liệu để được phát hiện theo thuật toán prescan.

### 8.1. Thứ tự xác định encoding của trình duyệt

Đối với tài liệu HTML nhận dưới dạng byte, thuật toán encoding sniffing của trình duyệt xét nhiều nguồn, trong đó có:

1. Byte Order Mark (BOM) ở đầu luồng, nếu có.
2. Encoding do người dùng chủ động ghi đè.
3. Charset trong metadata của tầng truyền tải, ví dụ tham số `charset` của HTTP `Content-Type`.
4. Khai báo trong nội dung HTML, thường là `<meta charset="UTF-8">` trong phần đầu tài liệu.
5. Các bước dự phòng của user agent nếu vẫn chưa xác định được.

Vì vậy, một header HTTP có charset không khớp với `meta charset` có thể khiến trình duyệt ưu tiên thông tin từ HTTP. Hãy giữ các nguồn khai báo nhất quán.

### 8.2. Quy tắc thực hành cho HTML

- Lưu tệp HTML thực sự bằng UTF-8.
- Đặt `<meta charset="UTF-8">` gần đầu `<head>`.
- Nếu có thể cấu hình HTTP response, dùng `Content-Type: text/html; charset=UTF-8`.
- Không để header khai báo một charset trong khi byte thực tế được lưu bằng charset khác.
- Không dựa vào việc trình duyệt tự đoán encoding cho tài liệu không có khai báo.

BOM có thể giúp một số định dạng/consumer nhận diện encoding, nhưng không nên dùng BOM để thay thế quy ước khai báo charset rõ ràng khi bạn kiểm soát được tài liệu và response.

## 9. Giới hạn của text/plain khi thiếu charset

`text/plain` mô tả văn bản thuần. Khác với HTML, nội dung văn bản thuần không có một cấu trúc chuẩn như `<meta charset>` để tự khai báo encoding.

Theo RFC 6657, giá trị charset mặc định của `text/plain` khi không có tham số charset vẫn là `US-ASCII`. Do đó, nếu server trả:

```http
Content-Type: text/plain
```

nhưng byte của tệp là văn bản UTF-8 có dấu tiếng Việt, client có thể giải mã sai nếu không có thông tin encoding khác phù hợp.

Ví dụ, tệp `Notes.java` có comment:

```java
// Xin chào, đây là ghi chú tiếng Việt.
class Notes {
    public static void main(String[] args) {
        System.out.println("Java");
    }
}
```

Oracle mô tả tệp `.java` được phục vụ với MIME type `text/plain`. Nếu response không có charset, đừng giả định client nào cũng sẽ hiển thị comment tiếng Việt đúng.

### 9.1. Cách xử lý khi cần văn bản UTF-8 rõ ràng

Nếu cần đảm bảo client giải mã văn bản thuần bằng UTF-8, response nên có:

```http
Content-Type: text/plain; charset=UTF-8
```

Lệnh CLI `jwebserver` không có tùy chọn riêng để đặt charset cho từng phần mở rộng hoặc từng tệp. Khi cần kiểm soát header, hãy dùng một server/handler do ứng dụng cấu hình và đặt `Content-Type` rõ ràng.

Không nên đổi `text/plain` thành `text/html` chỉ để trình duyệt xử lý ký tự theo một cách khác. MIME type phải mô tả đúng nội dung thực tế.

## 10. JSON: UTF-8 là quy tắc trao đổi, không cần charset parameter

JSON có quy tắc encoding riêng. Theo RFC 8259, JSON được trao đổi giữa các hệ thống không thuộc một closed ecosystem **MUST** được mã hóa bằng UTF-8.

Media type đăng ký cho JSON là:

```http
Content-Type: application/json
```

Đăng ký `application/json` không định nghĩa tham số `charset`. Do đó, không cần thêm `; charset=UTF-8` để làm JSON hợp lệ; điều quan trọng là byte JSON thực sự được mã hóa UTF-8.

RFC 8259 cũng quy định không thêm BOM vào đầu JSON được truyền qua mạng.

Lưu ý: đừng mặc định mọi bản JDK đều có cùng mapping cho phần mở rộng `.json` chỉ dựa trên tên phần mở rộng. Hãy kiểm tra response `Content-Type` của JDK đang chạy. Nếu cần MIME type chính xác và nhất quán cho JSON, dùng handler có thể đặt header theo hợp đồng của API.

## 11. Directory listing có charset rõ ràng khác với tệp tĩnh

Khi request tới thư mục không có index file, Simple Web Server tự tạo trang HTML directory listing. Đây là nội dung do server sinh ra, không phải byte của một tệp HTML có sẵn trong document root.

Implementation của Simple Web Server tạo listing bằng UTF-8 và gửi header:

```http
Content-Type: text/html; charset=UTF-8
```

Điều này khác với tệp HTML tĩnh được tra từ bảng MIME, ví dụ:

```http
Content-Type: text/html
```

Sự khác nhau là hợp lý:

- Directory listing do server tạo nên server biết chính xác encoding đã dùng khi tạo body.
- Tệp HTML tĩnh đã có byte từ trước; bảng MIME chỉ xác định media type, còn encoding cần được xác định từ metadata phù hợp của response hoặc từ chính định dạng HTML.

Không lấy header của directory listing để suy luận rằng mọi tệp HTML tĩnh đều được gửi kèm charset UTF-8.

## 12. Thực hành: xác minh MIME type và charset

### 12.1. Tạo document root

Tạo cấu trúc:

```text
demo/
└── public/
    ├── index.html
    ├── Example.java
    ├── message.txt
    └── mystery.customdata
```

Nội dung `public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Kiểm tra MIME và charset</title>
</head>
<body>
  <h1>Xin chào Java 18+</h1>
  <p>Kiểm tra tiếng Việt: ă â ê ô ơ ư đ.</p>
</body>
</html>
```

Nội dung `public/Example.java`:

```java
// Ghi chú tiếng Việt trong tệp Java.
class Example {
    public static void main(String[] args) {
        System.out.println("Xin chào");
    }
}
```

Nội dung `public/message.txt`:

```text
Xin chào, đây là văn bản UTF-8.
```

Nội dung `public/mystery.customdata` có thể là một chuỗi byte mẫu không thuộc phần mở rộng MIME đã biết.

**Lưu ý:** lưu các tệp văn bản trong ví dụ bằng UTF-8 để phép thử tập trung vào metadata HTTP, không bị lẫn với lỗi encoding từ editor.

### 12.2. Khởi động server

Từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

### 12.3. Kiểm tra header của từng tệp

```sh
curl -I http://127.0.0.1:8080/index.html
curl -I http://127.0.0.1:8080/Example.java
curl -I http://127.0.0.1:8080/message.txt
curl -I http://127.0.0.1:8080/mystery.customdata
```

Ghi lại các trường:

- Status code.
- `Content-Type`.
- Có hay không có tham số `charset`.
- `Content-Length`, nếu được gửi.

Đối chiếu hai mapping được tài liệu Oracle nêu trực tiếp: `.html` → `text/html`, `.java` → `text/plain`. Với các phần mở rộng khác, ghi lại kết quả thực tế từ JDK đang chạy.

### 12.4. Kiểm tra nội dung HTML

```sh
curl -i http://127.0.0.1:8080/index.html
```

Kiểm tra response header và nội dung body. Nếu header không có charset, xác nhận tệp HTML vẫn có `<meta charset="UTF-8">` ở phần đầu và byte tệp được lưu bằng UTF-8.

### 12.5. Kiểm tra directory listing

Tạo một thư mục không có index, ví dụ `public/downloads/`, rồi gửi:

```sh
curl -I http://127.0.0.1:8080/downloads/
```

So sánh `Content-Type` của listing với tệp HTML tĩnh. Listing do server tạo thường có `text/html; charset=UTF-8`.

### 12.6. Ghi nhận kết quả

| Tài nguyên | MIME type mong đợi/đã xác minh | Charset cần quan sát |
| --- | --- | --- |
| `index.html` | `text/html` theo tài liệu Oracle. | Kiểm tra header và `meta charset`. |
| `Example.java` | `text/plain` theo tài liệu Oracle. | Kiểm tra có charset không; không giả định UTF-8 được thêm tự động. |
| `message.txt` | Ghi MIME type thực tế của JDK. | Nếu là `text/plain`, lưu ý mặc định US-ASCII khi thiếu charset. |
| `mystery.customdata` | `application/octet-stream` nếu không có mapping. | Charset không áp dụng cho kiểu nhị phân tổng quát. |
| `downloads/` | `text/html` do server tạo listing. | Listing do server sinh có charset UTF-8. |

Sau khi hoàn tất, dừng server bằng **Ctrl+C**.

## 13. Khi cần tự đặt MIME type và charset bằng Java API

CLI `jwebserver` phù hợp khi chấp nhận bảng MIME tích hợp và hành vi phục vụ tĩnh mặc định. Nếu ứng dụng cần quy tắc rõ ràng cho từng loại tài nguyên, hãy dùng `HttpServer` và `HttpHandler` để tự đặt response header.

Ví dụ handler trả một văn bản UTF-8:

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class Utf8TextServer {
    public static void main(String[] args) throws Exception {
        var server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 8080), 0);

        server.createContext("/message.txt", exchange -> {
            byte[] body = "Xin chào từ Java".getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");

            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
    }
}
```

Trong ví dụ này, ứng dụng:

1. Chủ động tạo byte bằng `StandardCharsets.UTF_8`.
2. Chủ động khai báo `text/plain; charset=UTF-8`.
3. Gửi đúng số byte trong `Content-Length` thông qua `sendResponseHeaders`.
4. Đóng response body sau khi ghi xong.

Cách này giúp MIME type và charset nhất quán. Khi phục vụ tệp do người dùng cung cấp, ứng dụng vẫn phải xác minh định dạng nội dung trước khi chọn header; không tin phần mở rộng tệp một cách mù quáng.

## 14. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tệp lạ bị tải xuống thay vì hiển thị | Không có mapping MIME và server dùng `application/octet-stream`. | Kiểm tra phần mở rộng và đặt đúng MIME type bằng handler nếu cần. |
| Tệp HTML được trả là `text/plain` | Phần mở rộng hoặc mapping không đúng. | Kiểm tra tên tệp và `Content-Type` thực tế. |
| Java source được hiển thị như văn bản | `.java` được map thành `text/plain`. | Đây là hành vi dự kiến; jwebserver không biên dịch hay chạy mã Java. |
| Tiếng Việt trong HTML bị lỗi | Byte tệp và charset trình duyệt sử dụng không khớp. | Lưu tệp UTF-8, đặt meta charset sớm và cấu hình HTTP charset nếu có thể. |
| Tiếng Việt trong tệp text/plain bị lỗi | Header thiếu charset; mặc định MIME của text/plain là US-ASCII. | Dùng handler gửi `text/plain; charset=UTF-8`. |
| JSON bị parser từ chối | Byte không phải UTF-8 hợp lệ, nội dung sai JSON hoặc có BOM. | Ghi JSON UTF-8, không thêm BOM và kiểm tra nội dung. |
| Tên tệp đúng nhưng MIME type không như dự kiến | Bảng MIME tích hợp không có mapping hoặc khác với giả định. | Dùng `curl -I` để xem header và kiểm tra JDK thực tế. |
| Nghĩ JDK 18 tự thêm charset UTF-8 | Nhầm default charset của Java SE APIs với metadata HTTP. | Kiểm tra `Content-Type`; thêm charset trong HTTP handler nếu cần. |
| Directory listing có charset nhưng HTML tĩnh không có | Listing do server tạo với UTF-8; HTML tĩnh lấy MIME type từ bảng. | Khai báo charset trong HTML hoặc đặt header bằng handler. |

## 15. Bài tập tự kiểm tra

1. Chạy `jwebserver` với một tệp `.html` và một tệp `.java`. Ghi lại `Content-Type` và giải thích hai mapping được tài liệu Oracle nêu.
2. Tạo tệp với phần mở rộng không có mapping. Kiểm tra fallback `application/octet-stream`.
3. Đổi tên một tệp HTML thành phần mở rộng không được nhận diện. Quan sát MIME type và giải thích vì sao server không tự phân tích nội dung.
4. Lưu một trang HTML bằng UTF-8, bỏ tham số charset trong response và thêm `<meta charset="UTF-8">`. Kiểm tra trình duyệt hiển thị tiếng Việt.
5. Đặt `meta charset` sau 1.024 byte đầu tiên và giải thích vì sao không nên làm như vậy.
6. Gửi response `text/plain` không có charset và giải thích quy tắc US-ASCII của MIME cho loại này.
7. Tạo JSON chứa tiếng Việt bằng UTF-8. Giải thích vì sao `application/json` không cần tham số charset.
8. So sánh header của directory listing và một tệp HTML tĩnh. Giải thích vì sao listing có thể có charset UTF-8 trong khi tệp HTML tĩnh không có.
9. Chạy đoạn Java dùng `Charset.defaultCharset()`. Giải thích vì sao kết quả UTF-8 không làm thay đổi header HTTP của tệp tĩnh.
10. Viết một `HttpHandler` đặt `Content-Type: text/plain; charset=UTF-8` và gửi byte đã mã hóa bằng `StandardCharsets.UTF_8`.

**Tiêu chí hoàn thành:** bạn giải thích được MIME type được chọn từ bảng tích hợp, fallback `application/octet-stream`, phân biệt MIME type với charset, hiểu tác động thực tế của JEP 400 và biết kiểm tra/khai báo UTF-8 phù hợp với HTML, text/plain và JSON.

## 16. Tài liệu tham khảo

- [Oracle Java SE 25 — The jwebserver Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jwebserver.html): mô tả MIME type được tự động cấu hình bằng bảng tích hợp và ví dụ `.html` → `text/html`, `.java` → `text/plain`.
- [Oracle Java SE 26 — SimpleFileServer API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): mô tả `Content-Type` dựa trên best-guess content type từ system-wide `mimeTable`.
- [OpenJDK — FileServerHandler.java](https://github.com/openjdk/jdk/blob/master/src/jdk.httpserver/share/classes/sun/net/httpserver/simpleserver/FileServerHandler.java): implementation tra MIME table, dùng fallback `application/octet-stream`, gửi byte của tệp và tạo directory listing với `text/html; charset=UTF-8`.
- [Oracle JDK 27 Migration Guide — Default Charset](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): xác nhận từ JDK 18, UTF-8 là default charset của Java SE APIs.
- [RFC 6657 — Charset Parameter Handling in Textual Media Types](https://www.rfc-editor.org/rfc/rfc6657.html): cập nhật quy tắc charset cho media type `text/*`, trong đó `text/plain` vẫn mặc định US-ASCII nếu thiếu tham số charset.
- [WHATWG HTML Standard — Determining the Character Encoding](https://html.spec.whatwg.org/multipage/parsing.html#determining-the-character-encoding): thuật toán trình duyệt xác định charset qua BOM, HTTP metadata và khai báo trong tài liệu.
- [RFC 8259 — JSON, Section 8.1 and 11](https://www.rfc-editor.org/rfc/rfc8259.html): yêu cầu JSON trao đổi giữa các hệ thống dùng UTF-8 và đăng ký media type `application/json` không có charset parameter.
